// The switch at the end of a settings row: ArToggle without a label, so it takes only the
// 40px of its track (a labelless ArToggle still reserves room for the label).
import "components"

ArToggle {
    implicitWidth: implicitIndicatorWidth + leftPadding + rightPadding
}
