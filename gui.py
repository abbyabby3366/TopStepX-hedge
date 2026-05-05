import tkinter as tk
from tkinter import messagebox
import threading

# Global state for GUI
scraper_frame_visible = False
notif_frame_visible = False
scraper_frame = None
btn_toggle_scraper = None
notif_frame = None
btn_toggle_notif = None
gui_elements = {}

def toggle_scraper():
    global scraper_frame_visible, scraper_frame, btn_toggle_scraper
    if scraper_frame_visible:
        scraper_frame.grid_remove()
        btn_toggle_scraper.config(text="▶ Scraper Settings (Click to expand)")
    else:
        scraper_frame.grid()
        btn_toggle_scraper.config(text="▼ Scraper Settings (Click to collapse)")
    scraper_frame_visible = not scraper_frame_visible

def toggle_notifications():
    global notif_frame_visible, notif_frame, btn_toggle_notif
    if notif_frame_visible:
        notif_frame.grid_remove()
        btn_toggle_notif.config(text="▶ Notifications (Click to expand)")
    else:
        notif_frame.grid()
        btn_toggle_notif.config(text="▼ Notifications (Click to collapse)")
    notif_frame_visible = not notif_frame_visible

def save_gui_config(config_ref, save_callback):
    global gui_elements
    for key, ui_elem in gui_elements.items():
        if isinstance(ui_elem, tk.BooleanVar):
            config_ref[key] = ui_elem.get()
        else:
            val = ui_elem.get()
            if key in ["DEBUG_PORT", "NUM_ACCOUNTS_MULTIPLIER", "MT5_LOGIN"]:
                try: val = int(val)
                except: pass
            elif key in ["LOT_SIZE_MULTIPLIER"]:
                try: val = float(val)
                except: pass
            config_ref[key] = val
            
    save_callback(config_ref)
    messagebox.showinfo("Success", "Configuration saved!")

def launch_gui(config_ref, save_callback, start_server_callback):
    global gui_elements, scraper_frame_visible, notif_frame_visible
    global scraper_frame, btn_toggle_scraper, notif_frame, btn_toggle_notif
    
    root = tk.Tk()
    root.title("TopStep to MT5 Bridge Config")
    root.geometry("550x550")
    
    # ---------------- Scrollable Canvas Setup ----------------
    main_frame = tk.Frame(root)
    main_frame.pack(fill=tk.BOTH, expand=1)

    canvas = tk.Canvas(main_frame)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=1)

    scrollbar = tk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    canvas.configure(yscrollcommand=scrollbar.set)

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    scrollable_frame = tk.Frame(canvas)
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
    
    # Crucial Fix: Bind Configure to the inner frame, not the canvas!
    # This ensures the scroll region updates whenever accordions expand or collapse.
    scrollable_frame.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    # ---------------------------------------------------------

    title_lbl = tk.Label(scrollable_frame, text="TopStepX Copier Configuration", font=("Arial", 12, "bold"))
    title_lbl.grid(row=0, column=0, columnspan=2, pady=5)
    
    lbl_status = tk.Label(scrollable_frame, text="Status: Bridge is Active and Listening on Port 5000", font=("Arial", 9, "italic"), fg="green")
    lbl_status.grid(row=1, column=0, columnspan=2, pady=(0, 5))
    
    gui_elements = {}
    
    row = 2
    current_parent = scrollable_frame
    notif_row = 0
    scraper_row = 0
    notif_frame_visible = False
    scraper_frame_visible = False
    
    for key, val in config_ref.items():
        if key == "CHROME_PATH":
            btn_toggle_scraper = tk.Button(scrollable_frame, text="▶ Scraper Settings (Click to expand)", font=("Arial", 10, "bold"), fg="#0052cc", relief="flat", command=toggle_scraper, cursor="hand2")
            btn_toggle_scraper.grid(row=row, column=0, columnspan=2, pady=(10, 2))
            row += 1
            
            scraper_frame = tk.Frame(scrollable_frame)
            scraper_frame.grid(row=row, column=0, columnspan=2)
            scraper_frame.grid_remove() # hide initially
            row += 1
            
            current_parent = scraper_frame
            scraper_row = 0

        elif key == "REVERSE_TRADING":
            current_parent = scrollable_frame
            tk.Label(scrollable_frame, text="--- Trade Logic ---", font=("Arial", 10, "bold"), fg="#0052cc").grid(row=row, column=0, columnspan=2, pady=(10, 2))
            row += 1
            
        elif key == "MT5_LOGIN":
            current_parent = scrollable_frame
            tk.Label(scrollable_frame, text="--- MT5 Bridge Settings ---", font=("Arial", 10, "bold"), fg="#0052cc").grid(row=row, column=0, columnspan=2, pady=(10, 2))
            row += 1
            
        elif key == "WHATSAPP_GROUP_ID":
            btn_toggle_notif = tk.Button(scrollable_frame, text="▶ Notifications (Click to expand)", font=("Arial", 10, "bold"), fg="#0052cc", relief="flat", command=toggle_notifications, cursor="hand2")
            btn_toggle_notif.grid(row=row, column=0, columnspan=2, pady=(10, 2))
            row += 1
            
            notif_frame = tk.Frame(scrollable_frame)
            notif_frame.grid(row=row, column=0, columnspan=2)
            notif_frame.grid_remove() # hide initially
            row += 1
            
            current_parent = notif_frame
            notif_row = 0
            
        parent = current_parent
        if parent == notif_frame:
            r = notif_row
        elif parent == scraper_frame:
            r = scraper_row
        else:
            r = row
            
        lbl = tk.Label(parent, text=key, font=("Arial", 9))
        lbl.grid(row=r, column=0, sticky="e", padx=5, pady=2)
        
        if isinstance(val, bool):
            var = tk.BooleanVar(value=val)
            chk = tk.Checkbutton(parent, variable=var)
            chk.grid(row=r, column=1, sticky="w", padx=5)
            gui_elements[key] = var
        else:
            ent = tk.Entry(parent, width=45)
            ent.insert(0, str(val))
            ent.grid(row=r, column=1, padx=5, pady=2, sticky="w")
            gui_elements[key] = ent
            
        if parent == notif_frame:
            notif_row += 1
        elif parent == scraper_frame:
            scraper_row += 1
        else:
            row += 1
        
    btn_save = tk.Button(scrollable_frame, text="Save Config", bg="#4CAF50", fg="white", font=("Arial", 10, "bold"), command=lambda: save_gui_config(config_ref, save_callback))
    btn_save.grid(row=row, column=0, columnspan=2, pady=10)
    
    # Trigger background server
    start_server_callback()
    
    root.mainloop()
