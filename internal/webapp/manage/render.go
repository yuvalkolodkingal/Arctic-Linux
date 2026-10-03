package manage

import (
	"github.com/yuvalkolodkingal/o-tism/internal/webapp"
	"github.com/yuvalkolodkingal/o-tism/internal/webapp/icon"
)

// render writes the app's launcher entry and icons from its record and stored source icon
// (a letter icon when there is none). Callers hold the exclusive lock.
func (m *Manager) render(a *webapp.App) error {
	src, err := icon.LoadSource(m.Paths, a.ID)
	if err != nil {
		src, err = icon.Monogram(a.Name, a.Category)
		if err != nil {
			return err
		}
	}
	if err := icon.Install(m.Paths, a.IconName(), src); err != nil {
		return err
	}
	icon.Remove(m.Paths, a.ID, a.IconName())
	if err := m.Paths.WriteAutostart(a, false); err != nil {
		return err
	}
	return m.Paths.WriteDesktop(a)
}

func removeIcons(p webapp.Paths, id string) { icon.Remove(p, id, "") }

func touchHicolor(p webapp.Paths) { icon.Touch(p) }

// SaveAndRender writes a record and its launcher entry and icons under the exclusive lock
// (render-sample's offline fixtures).
func (m *Manager) SaveAndRender(a *webapp.App) error {
	return m.exclusive(func() error {
		if err := m.Paths.Save(a); err != nil {
			return err
		}
		return m.render(a)
	})
}
