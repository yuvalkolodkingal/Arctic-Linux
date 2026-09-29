// Package webapp is the core of Arctic's web apps (docs/BUILD-SPEC.md §11 "Web apps"): app ids,
// per-user paths, the registry (app.json under a flock), launcher entries and running-app
// bookkeeping. It never touches the network; the manager (cmd/arctic-webapp) and the window
// (cmd/arctic-webapp-host) both import it.
//
// A web app is a website with its own launcher entry, icon, window, Wayland app_id and signed-in
// profile. Its id is the GApplication id, the Wayland app_id, the .desktop basename, the D-Bus
// name and the first icon name:
//
//	org.arcticlinux.WebApp.<Slug>_<hash>
package webapp
