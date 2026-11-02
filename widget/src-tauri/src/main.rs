// NAVRYX SKY — віджет для Windows: вікно з вашим станом поверх усіх програм, значок у треї, автозапуск із Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};
use tauri_plugin_autostart::{MacosLauncher, ManagerExt};

const SITE: &str = "https://sky.navryx.com.ua";

fn show(app: &tauri::AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.unminimize();
        let _ = w.set_focus();
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show(app)))
        .plugin(tauri_plugin_autostart::init(MacosLauncher::LaunchAgent, None))
        .setup(|app| {
            // перший запуск: вмикаємо автозапуск із Windows (вимикається в меню значка)
            let al = app.autolaunch();
            if let Ok(dir) = app.path().app_config_dir() {
                let flag = dir.join("first-run-done");
                if !flag.exists() {
                    let _ = al.enable();
                    let _ = std::fs::create_dir_all(&dir);
                    let _ = std::fs::write(&flag, "1");
                }
            }
            let show_i = MenuItem::with_id(app, "show", "Показати віджет", true, None::<&str>)?;
            let top_i = CheckMenuItem::with_id(app, "top", "Поверх усіх вікон", true, true, None::<&str>)?;
            let auto_i = CheckMenuItem::with_id(app, "auto", "Запускати разом з Windows", true, al.is_enabled().unwrap_or(false), None::<&str>)?;
            let site_i = MenuItem::with_id(app, "site", "Відкрити повну мапу", true, None::<&str>)?;
            let reload_i = MenuItem::with_id(app, "reload", "Оновити", true, None::<&str>)?;
            let sep = PredefinedMenuItem::separator(app)?;
            let quit_i = MenuItem::with_id(app, "quit", "Вийти", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show_i, &top_i, &auto_i, &site_i, &reload_i, &sep, &quit_i])?;
            let (top_c, auto_c) = (top_i.clone(), auto_i.clone());
            TrayIconBuilder::with_id("tray")
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("NAVRYX SKY — повітряна обстановка")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_tray_icon_event(|tray, e| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = e {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window("main") {
                            if w.is_visible().unwrap_or(false) { let _ = w.hide(); } else { show(app); }
                        }
                    }
                })
                .on_menu_event(move |app, e| match e.id().as_ref() {
                    "show" => show(app),
                    "top" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.set_always_on_top(top_c.is_checked().unwrap_or(true));
                        }
                    }
                    "auto" => {
                        let al = app.autolaunch();
                        let _ = if auto_c.is_checked().unwrap_or(false) { al.enable() } else { al.disable() };
                    }
                    "site" => {
                        let _ = std::process::Command::new("explorer").arg(SITE).spawn();
                    }
                    "reload" => {
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.eval("location.reload()");
                        }
                    }
                    "quit" => app.exit(0),
                    _ => {}
                })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|w, e| {
            // хрестик ховає віджет у трей, а не закриває: тривоги мають доходити й далі
            if let WindowEvent::CloseRequested { api, .. } = e {
                let _ = w.hide();
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("NAVRYX SKY: не вдалося запустити віджет");
}
