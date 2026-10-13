package main

import (
	"context"
	"encoding/json"
	"net/http/httptest"
	"strings"
	"testing"
)

func testApp() *application {
	return &application{token: "session-token", origin: "http://127.0.0.1:1234", profiles: json.RawMessage(`[]`), shutdown: func() {}, runner: func(context.Context, []byte) ([]byte, string, error) {
		return []byte(`{"ok":true,"result":[],"error":null}`), "diagnostic\n", nil
	}}
}

func invoke(a *application, path, body, token, origin string) *httptest.ResponseRecorder {
	r := httptest.NewRequest("POST", a.origin+path, strings.NewReader(body))
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("X-App-Token", token)
	if origin != "" {
		r.Header.Set("Origin", origin)
	}
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	return w
}

func TestSessionAndOriginRequired(t *testing.T) {
	a := testApp()
	for _, pair := range [][2]string{{"", ""}, {"wrong", ""}, {a.token, "https://another-site.example"}} {
		if w := invoke(a, "/api/operation", `{"operation":"ports"}`, pair[0], pair[1]); w.Code != 403 {
			t.Fatalf("got %d", w.Code)
		}
	}
}

func TestOnlyKnownOperationsReachBackend(t *testing.T) {
	a := testApp()
	called := false
	a.runner = func(context.Context, []byte) ([]byte, string, error) { called = true; return nil, "", nil }
	for _, body := range []string{`null`, `[]`, `{`, `{"operation":"shell"}`, `{"operation":3}`} {
		if w := invoke(a, "/api/operation", body, a.token, a.origin); w.Code != 400 {
			t.Fatalf("got %d for %s", w.Code, body)
		}
	}
	if called {
		t.Fatal("invalid request reached helper")
	}
}

func TestOperationResponseAndConcurrency(t *testing.T) {
	a := testApp()
	w := invoke(a, "/api/operation", `{"operation":"ports"}`, a.token, a.origin)
	if w.Code != 200 || !strings.Contains(w.Body.String(), `"ok":true`) || !strings.Contains(w.Body.String(), `"logs":"diagnostic\n"`) {
		t.Fatal(w.Body.String())
	}
	a.busy.Lock()
	defer a.busy.Unlock()
	for _, path := range []string{"/api/operation", "/api/close"} {
		if w := invoke(a, path, `{"operation":"ports"}`, a.token, a.origin); w.Code != 409 {
			t.Fatalf("got %d", w.Code)
		}
	}
}

func TestPageSessionAndFileAccess(t *testing.T) {
	a := testApp()
	for _, item := range []struct {
		path string
		want int
	}{{"/", 403}, {"/?token=" + a.token, 200}, {"/qc_core.py", 404}, {"/runtime/python.exe", 404}} {
		r := httptest.NewRequest("GET", a.origin+item.path, nil)
		w := httptest.NewRecorder()
		a.ServeHTTP(w, r)
		if w.Code != item.want {
			t.Fatalf("%s got %d", item.path, w.Code)
		}
		if item.want == 200 && (strings.Contains(w.Body.String(), "{{APP_TOKEN}}") || !strings.Contains(w.Body.String(), a.token)) {
			t.Fatal("missing page session")
		}
	}
}

func TestForeignHostAndLargeBodyRejected(t *testing.T) {
	a := testApp()
	r := httptest.NewRequest("POST", a.origin+"/api/operation", nil)
	r.Host = "another-site.example"
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	if w.Code != 403 {
		t.Fatal("foreign Host accepted")
	}
	if w := invoke(a, "/api/operation", strings.Repeat("x", 33*1024), a.token, a.origin); w.Code != 413 {
		t.Fatal("oversize request accepted")
	}
}

func TestBoundedLogs(t *testing.T) {
	b := &tailBuffer{limit: 5}
	_, _ = b.Write([]byte("abc"))
	n, err := b.Write([]byte("defgh"))
	if string(b.data) != "defgh" || n != 5 || err != nil {
		t.Fatal("invalid bounded buffer")
	}
}

func TestBrowserDisconnectDoesNotCancelUSBOperation(t *testing.T) {
	a := testApp()
	a.runner = func(ctx context.Context, body []byte) ([]byte, string, error) {
		if ctx.Err() != nil {
			t.Fatal("browser cancellation interrupted USB operation")
		}
		return []byte(`{"ok":true}`), "", nil
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	r := httptest.NewRequest("POST", a.origin+"/api/operation", strings.NewReader(`{"operation":"flash","port":"COM3"}`)).WithContext(ctx)
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("X-App-Token", a.token)
	w := httptest.NewRecorder()
	a.ServeHTTP(w, r)
	if w.Code != 200 {
		t.Fatal("USB operation did not finish")
	}
}
