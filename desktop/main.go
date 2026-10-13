package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"crypto/subtle"
	"embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"
)

//go:embed web
var assets embed.FS

type backendRunner func(context.Context, []byte) ([]byte, string, error)

type application struct {
	token, origin, root string
	runner              backendRunner
	busy                sync.Mutex
	profiles            json.RawMessage
	shutdown            func()
}

func reply(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func failure(w http.ResponseWriter, status int, message string) {
	reply(w, status, map[string]any{"ok": false, "error": message})
}

func (a *application) authorized(r *http.Request) bool {
	return subtle.ConstantTimeCompare([]byte(r.Header.Get("X-App-Token")), []byte(a.token)) == 1 &&
		(r.Header.Get("Origin") == "" || r.Header.Get("Origin") == a.origin)
}

func (a *application) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("Referrer-Policy", "no-referrer")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
	if r.Host != strings.TrimPrefix(a.origin, "http://") {
		failure(w, http.StatusForbidden, "Open this app from its own window.")
		return
	}
	if strings.HasPrefix(r.URL.Path, "/api/") {
		if !a.authorized(r) {
			failure(w, http.StatusForbidden, "Reopen ESP32 Logger Flasher.exe to connect.")
			return
		}
		switch r.URL.Path {
		case "/api/profiles":
			if r.Method != http.MethodGet {
				failure(w, 405, "Use GET.")
				return
			}
			reply(w, 200, a.profiles)
		case "/api/operation":
			a.operation(w, r)
		case "/api/close":
			if r.Method != http.MethodPost {
				failure(w, 405, "Use POST.")
				return
			}
			if !a.busy.TryLock() {
				failure(w, 409, "Wait for the current operation to finish.")
				return
			}
			a.busy.Unlock()
			reply(w, 200, map[string]any{"ok": true})
			go func() { time.Sleep(150 * time.Millisecond); a.shutdown() }()
		default:
			http.NotFound(w, r)
		}
		return
	}
	if r.Method != http.MethodGet {
		failure(w, 405, "Use GET.")
		return
	}
	switch r.URL.Path {
	case "/":
		if subtle.ConstantTimeCompare([]byte(r.URL.Query().Get("token")), []byte(a.token)) != 1 {
			failure(w, 403, "Open ESP32 Logger Flasher.exe to start the app.")
			return
		}
		body, err := assets.ReadFile("web/index.html")
		if err != nil {
			failure(w, 500, "Application resources are missing.")
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(bytes.ReplaceAll(body, []byte("{{APP_TOKEN}}"), []byte(a.token)))
	case "/app.css", "/app.js":
		body, err := assets.ReadFile("web" + r.URL.Path)
		if err != nil {
			http.NotFound(w, r)
			return
		}
		if r.URL.Path == "/app.css" {
			w.Header().Set("Content-Type", "text/css; charset=utf-8")
		} else {
			w.Header().Set("Content-Type", "text/javascript; charset=utf-8")
		}
		_, _ = w.Write(body)
	case "/favicon.ico":
		w.WriteHeader(http.StatusNoContent)
	default:
		http.NotFound(w, r)
	}
}

func (a *application) operation(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		failure(w, 405, "Use POST.")
		return
	}
	if !strings.HasPrefix(r.Header.Get("Content-Type"), "application/json") {
		failure(w, 415, "Send JSON.")
		return
	}
	body, err := io.ReadAll(http.MaxBytesReader(w, r.Body, 32*1024))
	if err != nil {
		failure(w, 413, "Settings are too large.")
		return
	}
	var request map[string]json.RawMessage
	if json.Unmarshal(body, &request) != nil || request == nil {
		failure(w, 400, "Invalid request.")
		return
	}
	var op string
	if json.Unmarshal(request["operation"], &op) != nil {
		failure(w, 400, "Choose an operation.")
		return
	}
	switch op {
	case "ports", "detect", "flash", "info", "configure", "initialize_storage":
	default:
		failure(w, 400, "Unknown operation.")
		return
	}
	if !a.busy.TryLock() {
		failure(w, 409, "Wait for the current operation to finish.")
		return
	}
	defer a.busy.Unlock()
	// Reloading or closing the browser must not interrupt a flash write.
	ctx, cancel := context.WithTimeout(context.Background(), 15*time.Minute)
	defer cancel()
	out, logs, runErr := a.runner(ctx, body)
	var response map[string]any
	if json.Unmarshal(out, &response) != nil {
		message := "The flashing helper could not start. Extract the whole ZIP and try again."
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			message = "The operation timed out. Reconnect the board and try again."
		}
		failure(w, 500, message)
		return
	}
	if _, ok := response["ok"].(bool); !ok {
		failure(w, 500, "The flashing helper returned an invalid response.")
		return
	}
	if runErr != nil && response["ok"] == true {
		failure(w, 500, "The flashing helper stopped unexpectedly.")
		return
	}
	response["logs"] = logs
	reply(w, 200, response)
}

type tailBuffer struct {
	data  []byte
	limit int
}

func (b *tailBuffer) Write(p []byte) (int, error) {
	n := len(p)
	b.data = append(b.data, p...)
	if len(b.data) > b.limit {
		b.data = append([]byte(nil), b.data[len(b.data)-b.limit:]...)
	}
	return n, nil
}

func pythonRunner(root string) backendRunner {
	return func(ctx context.Context, body []byte) ([]byte, string, error) {
		python := filepath.Join(root, "runtime", "python.exe")
		if runtime.GOOS != "windows" && os.Getenv("ESP32_FLASHER_TEST_PYTHON") != "" {
			python = os.Getenv("ESP32_FLASHER_TEST_PYTHON")
		}
		cmd := exec.CommandContext(ctx, python, "-X", "utf8", filepath.Join(root, "desktop", "backend.py"))
		cmd.Dir = root
		cmd.Env = append(os.Environ(), "QC_DESKTOP_PACKAGED=1", "PYTHONUTF8=1", "PYTHONIOENCODING=utf-8")
		configureProcess(cmd)
		cmd.Stdin = bytes.NewReader(body)
		stdout, stderr := &tailBuffer{limit: 128 * 1024}, &tailBuffer{limit: 64 * 1024}
		cmd.Stdout, cmd.Stderr = stdout, stderr
		err := cmd.Run()
		return stdout.data, string(stderr.data), err
	}
}

func runApp() error {
	executable, err := os.Executable()
	if err != nil {
		return err
	}
	root := filepath.Dir(executable)
	if os.Getenv("ESP32_FLASHER_TEST_ROOT") != "" && runtime.GOOS != "windows" {
		root = os.Getenv("ESP32_FLASHER_TEST_ROOT")
	}
	for _, path := range []string{"desktop/backend.py", "qc_core.py", "profiles/boards.json", "firmware"} {
		if _, err := os.Stat(filepath.Join(root, path)); err != nil {
			return fmt.Errorf("Extract the complete ZIP before opening the app. Missing: %s", path)
		}
	}
	if runtime.GOOS == "windows" {
		if _, err := os.Stat(filepath.Join(root, "runtime", "python.exe")); err != nil {
			return fmt.Errorf("The bundled runtime is missing. Extract the complete ZIP again.")
		}
	}
	data, err := os.ReadFile(filepath.Join(root, "profiles", "boards.json"))
	if err != nil {
		return err
	}
	var profiles struct {
		Profiles json.RawMessage `json:"profiles"`
	}
	if err := json.Unmarshal(data, &profiles); err != nil {
		return err
	}
	listener, err := net.Listen("tcp4", "127.0.0.1:0")
	if err != nil {
		return err
	}
	defer listener.Close()
	secret := make([]byte, 32)
	if _, err := rand.Read(secret); err != nil {
		return err
	}
	a := &application{token: hex.EncodeToString(secret), origin: "http://" + listener.Addr().String(), root: root, runner: pythonRunner(root), profiles: profiles.Profiles}
	server := &http.Server{Handler: a, ReadHeaderTimeout: 5 * time.Second, ReadTimeout: 10 * time.Second, WriteTimeout: 16 * time.Minute, IdleTimeout: 60 * time.Second}
	a.shutdown = func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = server.Shutdown(ctx)
	}
	url := a.origin + "/?token=" + a.token
	if runtime.GOOS != "windows" || os.Getenv("ESP32_FLASHER_NO_BROWSER") == "1" {
		fmt.Println(url)
	}
	if os.Getenv("ESP32_FLASHER_NO_BROWSER") != "1" {
		if err := openBrowser(url); err != nil {
			return errors.New("Could not open your default browser. Set Chrome or Edge as the default browser and reopen the app.")
		}
	}
	err = server.Serve(listener)
	if errors.Is(err, http.ErrServerClosed) {
		return nil
	}
	return err
}

func main() {
	if err := runApp(); err != nil {
		notifyError(err.Error())
		os.Exit(1)
	}
}
