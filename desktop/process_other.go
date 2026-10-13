//go:build !windows

package main

import (
	"fmt"
	"os"
	"os/exec"
)

func configureProcess(cmd *exec.Cmd) {}
func openBrowser(url string) error   { return exec.Command("xdg-open", url).Start() }
func notifyError(message string)     { fmt.Fprintln(os.Stderr, message) }
