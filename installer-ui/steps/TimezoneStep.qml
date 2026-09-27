// Step 4 — Where are you? (INSTALL_STEPS[3]). Detected city card, Region + City
// dropdowns, "Set the time automatically" on. Local time comes from `date`
// run with TZ set, so it is right on the live system without extra engine calls.
import QtQuick
import Quickshell.Io
import ".."
import "../components"

StepPage {
    id: page
    stepId: "timezone"
    title: "Where are you?"
    lede: "We use this to set your clock and time zone."
    measure: 560
    valid: timezone !== ""
    helpText: "Your time zone sets the clock. If the detected city is wrong, pick your region and the nearest city. With automatic time on, the clock stays right using the internet."

    readonly property var opts: Wizard.step.options || {}
    readonly property var detected: opts.detected || null
    readonly property var regions: opts.regions || ({})
    readonly property var regionNames: Object.keys(regions).sort()
    property string timezone: (Wizard.step.data && Wizard.step.data.timezone) || (detected ? detected.timezone : "")
    property bool autoTime: Wizard.step.data && Wizard.step.data.auto_time !== undefined ? !!Wizard.step.data.auto_time : true
    property string region: regionOf(timezone)
    property string localTime: ""
    property string utcOffset: ""

    function regionOf(tz) {
        for (const r of regionNames)
            for (const c of regions[r])
                if (c.timezone === tz)
                    return r;
        return tz.indexOf("/") > 0 ? tz.split("/")[0] : (regionNames[0] || "");
    }
    function cityModel(r) {
        return (regions[r] || []).map(c => ({
                    value: c.timezone,
                    label: c.city
                }));
    }
    function commit(done) {
        Wizard.saveStep("timezone", {
            timezone: timezone,
            auto_time: autoTime
        }, done);
    }
    function focusFirst() {
        if (detected)
            detectedCard.forceActiveFocus();
        else
            regionSelect.combo.forceActiveFocus();
    }
    function fillForm(v) {
        if (v.timezone !== undefined) {
            timezone = v.timezone;
            region = regionOf(timezone);
        }
        if (v.auto_time !== undefined)
            autoTime = !!v.auto_time;
        if (v.open === "region")
            regionSelect.combo.popup.open();
        else if (v.open === "city")
            citySelect.combo.popup.open();
        else if (v.open === "")
            citySelect.combo.popup.close();
        return "ok";
    }

    onTimezoneChanged: clock.refresh()
    Component.onCompleted: clock.refresh()

    // Local time and UTC offset of the chosen zone.
    Process {
        id: clock
        function refresh() {
            if (page.timezone === "")
                return;
            running = false;
            environment = {
                TZ: page.timezone
            };
            running = true;
        }
        command: ["date", "+%H:%M %z"]
        stdout: StdioCollector {
            onStreamFinished: {
                const parts = text.trim().split(" ");
                if (parts.length !== 2)
                    return;
                page.localTime = parts[0];
                const z = parts[1];
                const h = parseInt(z.slice(1, 3), 10);
                const m = z.slice(3, 5);
                page.utcOffset = "UTC" + z[0] + h + (m !== "00" ? ":" + m : "");
            }
        }
    }
    Timer {
        interval: 30000
        running: true
        repeat: true
        onTriggered: clock.refresh()
    }

    Column {
        width: page.width
        spacing: Theme.space4

        ArCard {
            id: detectedCard
            visible: page.detected !== null
            width: parent.width
            choice: true
            iconName: "map-pin"
            title: page.detected ? page.detected.city : ""
            tag: page.detected && page.detected.source === "network" ? "Detected" : ""
            tagKind: "info"
            desc: {
                if (!page.detected)
                    return "";
                const when = page.localTime !== "" && page.timezone === page.detected.timezone ? " Local time is " + page.localTime + "." : "";
                return (page.detected.source === "network" ? "Found from your network." : "We couldn’t find your location, so this is our best guess.") + when;
            }
            selected: page.detected !== null && page.timezone === page.detected.timezone
            onClicked: {
                page.timezone = page.detected.timezone;
                page.region = page.regionOf(page.timezone);
            }
        }

        Row {
            width: parent.width
            spacing: Theme.space3
            ArSelect {
                id: regionSelect
                width: (parent.width - parent.spacing) / 2
                label: "Region"
                model: page.regionNames.map(r => ({
                            value: r,
                            label: r
                        }))
                value: page.region
                onActivated: v => {
                    page.region = v;
                    const cities = page.regions[v] || [];
                    if (cities.length && page.regionOf(page.timezone) !== v)
                        page.timezone = cities[0].timezone;
                }
            }
            ArSelect {
                id: citySelect
                width: (parent.width - parent.spacing) / 2
                label: "City"
                model: page.cityModel(page.region)
                value: page.timezone
                help: page.localTime !== "" && page.utcOffset !== "" && !detectedCard.selected ? "Local time " + page.localTime + " · " + page.utcOffset : ""
                onActivated: v => page.timezone = v
            }
        }

        ArToggle {
            text: "Set the time automatically from the internet"
            checked: page.autoTime
            onToggled: page.autoTime = checked
        }
    }
}
