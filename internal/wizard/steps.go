// Package wizard is the engine-owned installer flow (PLAN §5, BUILD-SPEC §4.1): the ten steps,
// their copy (design/guidelines/20-installer-copy.md), defaults, options and validation, and
// the navigation rules (Next validates, network auto-skips when wired and online, Goto only to
// done steps). The UI is a thin renderer of what this package returns.
package wizard

// Step ids, in order.
const (
	StepWelcome    = "welcome"
	StepKeyboard   = "keyboard"
	StepNetwork    = "network"
	StepTimezone   = "timezone"
	StepDisk       = "disk"
	StepEncryption = "encryption"
	StepAccount    = "account"
	StepApps       = "apps"
	StepSummary    = "summary"
	StepInstall    = "install"
	// StepDone is the final screen; it is not one of the ten rail steps.
	StepDone = "done"
)

// StepDef is a step's fixed copy.
type StepDef struct {
	ID      string
	Name    string // rail label (design StepIndicator)
	Title   string // screen heading
	Help    string // lede under the heading
	Note    string // bottom-left reassurance note
	Primary string // primary button
}

// Steps are the ten rail steps.
var Steps = []StepDef{
	{StepWelcome, "Welcome", "Welcome to Arctic Linux",
		"This takes about 10 minutes. First, pick the language you’d like to use.",
		"Nothing is changed on this computer until the Summary step.", "Next"},
	{StepKeyboard, "Keyboard", "Choose your keyboard layout",
		"This is how the keys on your keyboard will type. You can add more layouts later.", "", "Next"},
	{StepNetwork, "Network", "Connect to the internet",
		"Pick a Wi-Fi network or plug in a cable.", "", "Next"},
	{StepTimezone, "Time zone", "Where are you?",
		"We use this to set your clock and time zone.", "", "Next"},
	{StepDisk, "Disk", "How should we install?", "",
		"Nothing is erased until you confirm on the Summary step.", "Next"},
	{StepEncryption, "Encryption", "Create an encryption passphrase",
		"You’ll type this each time the computer starts, before logging in.", "", "Next"},
	{StepAccount, "Account", "Create your account", "", "", "Next"},
	{StepApps, "Apps", "Choose your apps",
		"We’ve ticked our favourites. Change anything — you can add or remove apps later.", "", "Next"},
	{StepSummary, "Summary", "Ready to install",
		"Check everything below. Nothing has been written to your disk yet.", "", "Erase disk and install"},
	{StepInstall, "Install", "Installing Arctic Linux",
		"You can leave this running. Keep the computer plugged in.", "Don’t remove the USB stick yet.", ""},
}

// DoneDef is the copy of the final screen ({n} and {first name} are filled in by GetStep).
var DoneDef = StepDef{StepDone, "Done", "Arctic Linux is ready",
	"Everything is installed, including {n} apps. Welcome aboard, {first}.", "", "Restart now"}

// Copy used by several screens (design/guidelines/20-installer-copy.md and the design mockups).
const (
	CopyNetworkWhyTitle = "Why do I need the internet?"
	CopyNetworkWhy      = "Arctic Linux downloads the apps you pick and the latest security updates while it installs, so you start up to date."
	CopyEraseTitle      = "Erase disk and install"
	CopyEraseDesc       = "Replaces everything on this disk with Arctic Linux. Your files are encrypted, so they stay private if the laptop is lost."
	CopyEraseWarning    = "All files on this disk will be erased. Back up anything you want to keep first."
	CopyPassphraseWarn  = "If you forget this passphrase, no one can recover your files — not even us. Write it down somewhere safe."
	CopyPassphraseHelp  = "Longer is stronger — a short sentence works well."
	CopyNoEncryptWarn   = "Without encryption, anyone who gets hold of this computer can read your files."
	CopyUsernameHint    = "Filled in from your name."
	CopyHostnameHint    = "Suggested from your name and computer"
	CopyHostnameHelp    = "Suggested from your name and computer. This is how other devices see it."
	CopyWhileYouWait    = "Super + Space opens the launcher. Super + Enter opens a terminal. Super + arrows move between windows."
	CopyRemoveUSBTitle  = "Remove the USB stick"
	CopyRemoveUSB       = "Take it out now, then restart. Your computer will start Arctic Linux and ask for your disk passphrase."
	CopyRemoveUSBNoLUKS = "Take it out now, then restart. Your computer will start Arctic Linux."
)

// Status lines during install (design/guidelines/20-installer-copy.md).
const (
	StatusDisk     = "Preparing the disk…"
	StatusCopy     = "Copying Arctic Linux…"
	StatusSetup    = "Setting up Arctic Linux…"
	StatusBoot     = "Getting your computer ready to start Arctic Linux…"
	StatusRemove   = "Removing the apps you didn’t pick…"
	StatusAccount  = "Setting up your account…"
	StatusTidy     = "Almost there — tidying up…"
	StatusFinished = "Arctic Linux is installed."
)

// Substep ids and labels of the install screen.
var Substeps = []struct{ ID, Label string }{
	{"disk", "Preparing the disk"},
	{"system", "Copying Arctic Linux"},
	{"apps", "Installing your apps"},
	{"finish", "Setting up your account"},
}

// StepIndex returns the position of a rail step, or -1.
func StepIndex(id string) int {
	for i, s := range Steps {
		if s.ID == id {
			return i
		}
	}
	return -1
}

// FindStep returns a step's definition (also for "done").
func FindStep(id string) (StepDef, bool) {
	if id == StepDone {
		return DoneDef, true
	}
	if i := StepIndex(id); i >= 0 {
		return Steps[i], true
	}
	return StepDef{}, false
}
