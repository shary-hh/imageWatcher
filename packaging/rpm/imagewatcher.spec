%global debug_package %{nil}

Name:           imagewatcher
Version:        1.25.23
Release:        1%{?dist}
Summary:        Captura, edicion y grabacion de pantalla para Linux

License:        MIT
URL:            https://github.com/shary-hh/imageWatcher
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch

BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel
BuildRequires:  pyproject-rpm-macros

Requires:       python3-gobject
Requires:       python3-cairo
Requires:       python3-pillow
Requires:       python3-xlib
Requires:       gtk3
Requires:       (ffmpeg or ffmpeg-free)
Recommends:     xdg-desktop-portal
Recommends:     libnotify

%description
imageWatcher es una suite de captura de pantalla para Linux con editor de
imagenes, herramientas de diseno (selector de color, lupa, regla,
transportador, pizarra), grabacion de video, atajos globales y bandeja del
sistema. Funciona en X11 y Wayland.

%prep
%autosetup -n %{name}-%{version}

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files imagewatcher

install -Dpm0644 packaging/assets/imagewatcher.svg \
    %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/imagewatcher.svg
install -Dpm0644 packaging/rpm/imagewatcher.desktop \
    %{buildroot}%{_datadir}/applications/imagewatcher.desktop

%post
update-desktop-database -q %{_datadir}/applications || :
gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor || :

%postun
update-desktop-database -q %{_datadir}/applications || :
gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor || :

%files -f %{pyproject_files}
%doc README.md
%{_bindir}/imagewatcher
%{_datadir}/applications/imagewatcher.desktop
%{_datadir}/icons/hicolor/scalable/apps/imagewatcher.svg

%changelog
* Fri Nov 27 2026 imageWatcher contributors <noreply@example.com> - 1.25.23-1
- Initial RPM packaging.
