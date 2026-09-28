package wizard

import (
	"fmt"
	"strings"

	"github.com/yuvalkolodkingal/o-tism/internal/catalog"
	"github.com/yuvalkolodkingal/o-tism/internal/protocol"
)

// Copy for drivers (Summary, Network and Done screens).
const (
	CopySecureBootTitle = "One more step when the computer restarts"
	CopySecureBootIntro = "Secure Boot is on, so this computer only starts drivers it trusts. The first time it restarts, confirm the key Arctic Linux signed your driver with:"
	CopySecureBootNote  = "Missed the blue screen? Arctic Linux still starts, only without the driver. Run “sudo mokutil --import /etc/pki/akmods/certs/public_key.der” in a terminal, pick any password, restart and type it there."
	CopyMOKFailedTitle  = "Your driver needs Secure Boot’s approval"
	CopyMOKFailedIntro  = "Arctic Linux couldn’t ask this computer to trust your driver’s key, so the driver won’t start while Secure Boot is on. After restarting:"
)

// MOKKeyPath is the akmods public key the installer asks shim to enroll.
const MOKKeyPath = "/etc/pki/akmods/certs/public_key.der"

// SecureBootSteps are the steps of shim's MokManager ("Perform MOK management") for code.
// later says the driver is only installed at first boot (offline): the blue screen then
// comes on the restart after that.
func SecureBootSteps(code string, later bool) *protocol.SecureBootInfo {
	title, intro, first := CopySecureBootTitle, CopySecureBootIntro,
		"Restart. A blue screen, “Perform MOK management”, appears — press any key within 10 seconds."
	if later {
		title = "One more step once your driver is installed"
		intro = "Secure Boot is on, so this computer only starts drivers it trusts. Your driver is installed the first time Arctic Linux is online; keep this code for the restart after that:"
		first = "Restart once the driver is installed. A blue screen, “Perform MOK management”, appears — press any key within 10 seconds."
	}
	return &protocol.SecureBootInfo{
		Code:  code,
		Title: title,
		Intro: intro,
		Steps: []string{
			first,
			"Choose “Enroll MOK”, then “Continue”, then “Yes”.",
			"Type the one-time code " + code + " with the number keys above the letters, then press Enter.",
			"Choose “Reboot”. Your driver starts from now on.",
		},
		Note: CopySecureBootNote,
	}
}

// SecureBootFailed says how to enroll the key by hand when mokutil failed during the install.
func SecureBootFailed() *protocol.SecureBootInfo {
	return &protocol.SecureBootInfo{
		Title: CopyMOKFailedTitle,
		Intro: CopyMOKFailedIntro,
		Steps: []string{
			"Open a terminal and run “sudo mokutil --import " + MOKKeyPath + "”. Pick a password you’ll remember for a minute.",
			"Restart. On the blue “Perform MOK management” screen choose “Enroll MOK”, “Continue”, “Yes”, type that password, then “Reboot”.",
		},
		Note:   "Or turn Secure Boot off in your computer’s firmware settings.",
		Failed: true,
	}
}

// DriverResult is the Done screen line for a driver and what happened to it. mok says the
// signing key is waiting to be enrolled (the driver starts only after that).
func DriverResult(m *catalog.Module, status string, mok bool) protocol.DriverResult {
	noun := driverNoun(m)
	dev := m.Fill("{device}")
	var text string
	switch status {
	case protocol.DriverInstalled:
		text = fmt.Sprintf("The %s for your %s starts after you restart.", noun, dev)
		if mok && m.AkmodName() != "" {
			text = fmt.Sprintf("The %s for your %s starts once you’ve confirmed its key (below).", noun, dev)
		}
	case protocol.DriverDeferred:
		text = fmt.Sprintf("The %s for your %s is installed the first time Arctic Linux is online. Restart once more after that.", noun, dev)
	default:
		status = protocol.DriverSkipped
		text = fmt.Sprintf("The %s wasn’t installed. Your %s uses the open-source driver.", noun, dev)
	}
	return protocol.DriverResult{ID: m.ID, Name: m.Name, Device: m.Device, Status: status, Text: text}
}

// driverNoun is a driver's name in a sentence ("NVIDIA driver", "Broadcom Wi-Fi driver").
func driverNoun(m *catalog.Module) string {
	if m.Short != "" && strings.HasSuffix(m.Short, "driver") {
		return m.Short
	}
	return m.Name
}

// SetDriverResults records the drivers' outcome for the Done screen.
func (w *Wizard) SetDriverResults(drivers []protocol.DriverResult, sb *protocol.SecureBootInfo) {
	w.DriverResults, w.SecureBoot = drivers, sb
}

// driversSummary is the Summary's "Drivers" row: each ticked driver with its device, and the
// key enrolment when Secure Boot is on. ok is false when no driver was detected (no row).
func (w *Wizard) driversSummary() (string, bool) {
	cat := w.env.Catalog()
	if len(cat.DetectedDrivers()) == 0 {
		return "", false
	}
	var parts []string
	akmod := false
	for _, m := range cat.Drivers(w.Data.Apps.Selection) {
		parts = append(parts, fmt.Sprintf("%s for your %s", m.Name, m.Fill("{device}")))
		if m.AkmodName() != "" {
			akmod = true
		}
	}
	if len(parts) == 0 {
		return "None — your hardware keeps its open-source drivers", true
	}
	v := strings.Join(parts, "; ")
	if akmod && w.env.Hardware().SecureBoot && w.env.Firmware() == "uefi" {
		v += ". Secure Boot is on: you’ll confirm the driver’s key once after restarting"
	}
	return v, true
}

// driverHint is the Network step's note about a Wi-Fi card that only works once its driver
// is installed ("" when there is none).
func (w *Wizard) driverHint() string {
	for _, m := range w.env.Catalog().DetectedDrivers() {
		if m.NetworkHint != "" {
			return m.Fill(m.NetworkHint)
		}
	}
	return ""
}
