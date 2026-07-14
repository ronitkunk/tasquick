import os
import time
import glob
import uuid
from datetime import datetime
import yaml
import sys
from PIL import Image, ImageDraw, ImageFont

# --- CONFIGURATION ---
YAML_PATH = os.path.abspath(sys.argv[1])
LOOP_INTERVAL_SECONDS = 15

# Canvas Base Size
WIDTH, HEIGHT = 1920, 1080
BG_COLOR = (0, 0, 0)        # Dark Slate
GRID_COLOR = (128, 128, 128)      # Muted Gray
TEXT_COLOR = (255, 255, 255)   # White/Off-white
WARN_COLOR = (255, 128, 128)   # Soft Red
DUE_DATE_COLOR = (128, 128, 255)  # Soft Blue

# --- DIRECTORY PATHING SETUP ---
YAML_DIR = os.path.dirname(YAML_PATH)
WALLPAPER_DIR = os.path.join(YAML_DIR, "tasquick_wallpapers")
os.makedirs(WALLPAPER_DIR, exist_ok=True)

def set_mac_wallpaper(path):
    """
    Forces the wallpaper update onto every active desktop object,
    overriding individual space isolation blocks.
    """
    script = (
        'tell application "System Events"\n'
        '    tell every desktop\n'
        f'        set picture to "{path}"\n'
        '    end tell\n'
        'end tell'
    )
    os.system(f"osascript -e '{script}'")

def clean_old_wallpapers():
    """Wipes old tracking files to prevent folder bloat."""
    files = glob.glob(os.path.join(WALLPAPER_DIR, "tasquick_*.png"))
    for f in files:
        try:
            os.remove(f)
        except OSError:
            pass

def load_tasks():
    if not os.path.exists(YAML_PATH):
        return []
    with open(YAML_PATH, 'r') as f:
        return yaml.safe_load(f) or []

def process_and_draw():
    tasks = load_tasks()
    
    # Initialize Image Canvas
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype("Verdana", 22)
        font_item = ImageFont.truetype("Verdana", 16)
    except IOError:
        font_title = font_item = ImageFont.load_default()

    # --- CALCULATE MIDDLE 50% BOUNDING BOX ---
    box_w = WIDTH // 2
    box_h = HEIGHT // 2
    x_min = (WIDTH - box_w) // 2
    x_max = x_min + box_w
    y_min = (HEIGHT - box_h) // 2
    y_max = y_min + box_h
    x_mid = x_min + (box_w // 2)
    y_mid = y_min + (box_h // 2)

    # Draw the Centered 2x2 Grid Lines and outer border inside the middle 50% zone
    draw.line([(x_mid, y_min), (x_mid, y_max)], fill=GRID_COLOR, width=3)
    draw.line([(x_min, y_mid), (x_max, y_mid)], fill=GRID_COLOR, width=3)
    draw.rectangle([x_min, y_min, x_max - 1, y_max - 1], outline=GRID_COLOR, width=3)

    # Define Quadrant Coordinate Boundaries mapped to the center core
    quadrants = {
        "Q1": {"title": "URGENT, IMPORTANT", "box": (x_mid, y_min, x_max, y_mid)},
        "Q2": {"title": "NOT URGENT, IMPORTANT", "box": (x_min, y_min, x_mid, y_mid)},
        "Q3": {"title": "URGENT, NOT IMPORTANT", "box": (x_mid, y_mid, x_max, y_max)},
        "Q4": {"title": "NOT URGENT, NOT IMPORTANT", "box": (x_min, y_mid, x_mid, y_max)}
    }

    bucketed = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

    for task in tasks:
        is_urgent = task.get('urgent', False)
        is_important = task.get('important', False)
        due = task.get('due_date')
        task_warning = None
        
        if is_urgent and not due:
            task_warning = "missing due date"
        elif due:
            try:
                due_dt = datetime.strptime(str(due), "%Y-%m-%d")
                today = datetime.now().date()
                due_date = due_dt.date()
                days_left = (due_date - today).days

                if due_date < today:
                    overdue_days = (today - due_date).days
                    task_warning = f"overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}"
                elif not is_urgent and days_left <= 7:
                    task_warning = "due soon: consider marking urgent"
            except ValueError:
                pass

        task['warning'] = task_warning

        if Lech := (is_important, is_urgent):
            if Lech == (True, True): bucketed["Q1"].append(task)
            elif Lech == (True, False): bucketed["Q2"].append(task)
            elif Lech == (False, True): bucketed["Q3"].append(task)
            else: bucketed["Q4"].append(task)

    for q_id, q_tasks in bucketed.items():
        if q_id in ["Q1", "Q3"]:
            q_tasks.sort(key=lambda x: str(x.get('due_date', '9999-12-31')))
        else:
            q_tasks.sort(key=lambda x: str(x.get('added_date', '1970-01-01')))

    # Render Text into Layout Frame
    for q_id, info in quadrants.items():
        x_start, y_start, _, _ = info["box"]
        
        draw.text((x_start + 20, y_start + 20), info["title"], fill=TEXT_COLOR, font=font_title)
        
        y_offset = y_start + 65
        for task in bucketed[q_id]:
            name = task.get('name', 'Unnamed Task')
            due_date = task.get('due_date')
            due_str = str(due_date) if due_date else None
            
            task_warning = task.get('warning')
            display_text = f"• {name}"
            
            draw.text((x_start + 25, y_offset), display_text, fill=TEXT_COLOR, font=font_item)
            
            if due_str:
                draw.text((x_start + 25, y_offset + 20), f"Due: {due_str}", fill=DUE_DATE_COLOR, font=font_item)
            elif task_warning:
                draw.text((x_start + 25, y_offset + 20), task_warning, fill=WARN_COLOR, font=font_item)

            if due_str and task_warning:
                draw.text((x_start + 25, y_offset + 40), task_warning, fill=WARN_COLOR, font=font_item)

            extra_lines = 1 if (due_str or task_warning) else 0
            if due_str and task_warning:
                extra_lines += 1
            y_offset += 30 + (extra_lines * 20)

    # Footer text aligned underneath the center grid area
    timestamp = f"Last Update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    footer_link = "github.com/ronitkunk/tasquick"
    draw.text((x_min, y_max + 20), timestamp, fill=GRID_COLOR, font=font_item, anchor="lm")
    draw.text((x_max, y_max + 20), footer_link, fill=GRID_COLOR, font=font_item, anchor="rm")

    # --- FILER CLEANUP & UNIQUE RENDER PIPELINE ---
    clean_old_wallpapers()
    unique_filename = f"tasquick_{uuid.uuid4().hex}.png"
    new_wallpaper_path = os.path.join(WALLPAPER_DIR, unique_filename)
    
    img.save(new_wallpaper_path)
    set_mac_wallpaper(new_wallpaper_path)

if __name__ == "__main__":
    print("Matrix Desktop Engine active. Monitoring tasks.yaml...")
    
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Initializing desktop matrix...")
        process_and_draw()
    except Exception as e:
        print(f"Initial render failed: {e}")

    last_mtime = os.path.getmtime(YAML_PATH) if os.path.exists(YAML_PATH) else 0
    
    while True:
        try:
            if os.path.exists(YAML_PATH):
                current_mtime = os.path.getmtime(YAML_PATH)
                if current_mtime > last_mtime:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Change detected. Re-rendering matrix...")
                    process_and_draw()
                    last_mtime = current_mtime
        except Exception as e:
            print(f"Error encountered inside loop: {e}")
            
        time.sleep(LOOP_INTERVAL_SECONDS)
