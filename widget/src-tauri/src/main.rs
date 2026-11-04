// NAVRYX SKY — віджет для Windows: вікно з вашим станом поверх усіх програм, значок у треї, автозапуск із Windows.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    LogicalSize, Manager, PhysicalPosition, WindowEvent,
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

// Налаштування вікна (04.11): розмір, кут екрана, «поверх усіх вікон» — зберігаються між запусками.
// Те, що показувати всередині (тема, прозорість, текст, що саме) — у самому віджеті, кнопка ⚙.
fn cfg_path(app: &tauri::AppHandle) -> Option<std::path::PathBuf> {
    app.path().app_config_dir().ok().map(|d| d.join("window.json"))
}

fn cfg_load(app: &tauri::AppHandle) -> serde_json::Value {
    cfg_path(app)
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|t| serde_json::from_str(&t).ok())
        .unwrap_or_else(|| serde_json::json!({"size": "m", "corner": "free", "top": true}))
}

fn cfg_set(app: &tauri::AppHandle, key: &str, val: serde_json::Value) {
    let mut c = cfg_load(app);
    c[key] = val;
    if let Some(p) = cfg_path(app) {
        let _ = std::fs::create_dir_all(p.parent().unwrap());
        let _ = std::fs::write(p, c.to_string());
    }
}

fn size_of(k: &str) -> (f64, f64) {
    match k {
        "s" => (300.0, 210.0),
        "l" => (540.0, 440.0),
        _ => (400.0, 320.0),
    }
}

fn apply_size(app: &tauri::AppHandle, k: &str) {
    if let Some(w) = app.get_webview_window("main") {
        let (a, b) = size_of(k);
        let _ = w.set_size(LogicalSize::new(a, b));
    }
}

fn apply_corner(app: &tauri::AppHandle, k: &str) {
    if k == "free" {
        return;
    }
    if let Some(w) = app.get_webview_window("main") {
        if let (Ok(Some(m)), Ok(sz)) = (w.current_monitor(), w.outer_size()) {
            let (mp, ms) = (m.position(), m.size());
            let pad = (16.0 * m.scale_factor()) as i32;
            let bottom = (56.0 * m.scale_factor()) as i32; // панель завдань
            let x = if k.ends_with('l') { mp.x + pad } else { mp.x + ms.width as i32 - sz.width as i32 - pad };
            let y = if k.starts_with('t') { mp.y + pad } else { mp.y + ms.height as i32 - sz.height as i32 - bottom };
            let _ = w.set_position(PhysicalPosition::new(x, y));
        }
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
            let cfg = cfg_load(app.handle());
            let size0 = cfg["size"].as_str().unwrap_or("m").to_string();
            let corner0 = cfg["corner"].as_str().unwrap_or("free").to_string();
            let top0 = cfg["top"].as_bool().unwrap_or(true);
            apply_size(app.handle(), &size0);
            apply_corner(app.handle(), &corner0);
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_always_on_top(top0);
            }
            let show_i = MenuItem::with_id(app, "show", "Показати віджет", true, None::<&str>)?;
            let top_i = CheckMenuItem::with_id(app, "top", "Поверх усіх вікон", true, top0, None::<&str>)?;
            let sizes = [("s", "Малий"), ("m", "Середній"), ("l", "Великий")];
            let corners = [("tl", "Угорі ліворуч"), ("tr", "Угорі праворуч"), ("bl", "Унизу ліворуч"), ("br", "Унизу праворуч"), ("free", "Там, де залишив")];
            let size_items: Vec<CheckMenuItem<tauri::Wry>> = sizes.iter()
                .map(|(k, l)| CheckMenuItem::with_id(app, format!("size:{k}"), *l, true, size0 == *k, None::<&str>))
                .collect::<Result<_, _>>()?;
            let corner_items: Vec<CheckMenuItem<tauri::Wry>> = corners.iter()
                .map(|(k, l)| CheckMenuItem::with_id(app, format!("corner:{k}"), *l, true, corner0 == *k, None::<&str>))
                .collect::<Result<_, _>>()?;
            let size_refs: Vec<&dyn tauri::menu::IsMenuItem<tauri::Wry>> = size_items.iter().map(|i| i as &dyn tauri::menu::IsMenuItem<tauri::Wry>).collect();
            let corner_refs: Vec<&dyn tauri::menu::IsMenuItem<tauri::Wry>> = corner_items.iter().map(|i| i as &dyn tauri::menu::IsMenuItem<tauri::Wry>).collect();
            let size_m = Submenu::with_items(app, "Розмір вікна", true, &size_refs)?;
            let corner_m = Submenu::with_items(app, "Розташування", true, &corner_refs)?;
            let hint_i = MenuItem::with_id(app, "hint", "Тема, прозорість, що показувати: ⚙ у віджеті", false, None::<&str>)?;
            let auto_i = CheckMenuItem::with_id(app, "auto", "Запускати разом з Windows", true, al.is_enabled().unwrap_or(false), None::<&str>)?;
            let site_i = MenuItem::with_id(app, "site", "Відкрити повну мапу", true, None::<&str>)?;
            let reload_i = MenuItem::with_id(app, "reload", "Оновити", true, None::<&str>)?;
            let sep = PredefinedMenuItem::separator(app)?;
            let quit_i = MenuItem::with_id(app, "quit", "Вийти", true, None::<&str>)?;
            let sep2 = PredefinedMenuItem::separator(app)?;
            let menu = Menu::with_items(app, &[&show_i, &size_m, &corner_m, &top_i, &auto_i, &hint_i, &sep2, &site_i, &reload_i, &sep, &quit_i])?;
            let (top_c, auto_c) = (top_i.clone(), auto_i.clone());
            let (size_c, corner_c) = (size_items.clone(), corner_items.clone());
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
                    id if id.starts_with("size:") => {
                        let k = &id[5..];
                        for (i, (kk, _)) in sizes.iter().enumerate() {
                            let _ = size_c[i].set_checked(*kk == k);
                        }
                        apply_size(app, k);
                        let corner = cfg_load(app)["corner"].as_str().unwrap_or("free").to_string();
                        apply_corner(app, &corner);
                        cfg_set(app, "size", serde_json::json!(k));
                    }
                    id if id.starts_with("corner:") => {
                        let k = &id[7..];
                        for (i, (kk, _)) in corners.iter().enumerate() {
                            let _ = corner_c[i].set_checked(*kk == k);
                        }
                        apply_corner(app, k);
                        cfg_set(app, "corner", serde_json::json!(k));
                    }
                    "show" => show(app),
                    "top" => {
                        let on = top_c.is_checked().unwrap_or(true);
                        if let Some(w) = app.get_webview_window("main") {
                            let _ = w.set_always_on_top(on);
                        }
                        cfg_set(app, "top", serde_json::json!(on));
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
