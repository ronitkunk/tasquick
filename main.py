import glob
import os
import sys
import time
import uuid
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import torch
import yaml

# --- CONFIGURATION ---
YAML_PATH = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.abspath(
    os.path.join(os.path.dirname(__file__), "tasks.yaml")
)
LOOP_INTERVAL_SECONDS = 15

WIDTH, HEIGHT = 1920, 1080
TABLE_WIDTH_PERCENT = 0.80
TABLE_HEIGHT_PERCENT = 0.80
BG_COLOR = (0.0, 0.0, 0.0)
GRID_COLOR = (0.5, 0.5, 0.5)
TEXT_COLOR = (1.0, 1.0, 1.0)
WARN_COLOR = (1.0, 0.5, 0.5)
DUE_DATE_COLOR = (0.5, 0.5, 1.0)
RISK_COLOR = (1.0, 0.31, 0.31)
ALLOCATION_COLORMAP = "PiYG"

YAML_DIR = os.path.dirname(YAML_PATH)
WALLPAPER_DIR = os.path.join(YAML_DIR, "tasquick_wallpapers")
os.makedirs(WALLPAPER_DIR, exist_ok=True)


def set_mac_wallpaper(path: str) -> None:
    """Set the generated image as the wallpaper on every macOS desktop."""
    script = (
        'tell application "System Events"\n'
        '    tell every desktop\n'
        f'        set picture to "{path}"\n'
        '    end tell\n'
        'end tell'
    )
    try:
        os.system(f"osascript -e '{script}'")
    except Exception as exc:
        print(f"Wallpaper update skipped: {exc}")


def clean_old_wallpapers() -> None:
    """Remove prior generated wallpapers so the folder does not accumulate stale files."""
    for file_path in glob.glob(os.path.join(WALLPAPER_DIR, "tasquick_*.png")):
        try:
            os.remove(file_path)
        except OSError:
            continue


def load_tasks() -> List[Dict[str, Any]]:
    """Load task definitions from YAML, returning an empty list if the file is missing."""
    if not os.path.exists(YAML_PATH):
        return []

    with open(YAML_PATH, "r", encoding="utf-8") as handle:
        raw_tasks = yaml.safe_load(handle) or []

    if not isinstance(raw_tasks, list):
        return []

    return raw_tasks


def preprocess_tasks(tasks: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Normalise task values, add derived fields, and compute a warning message per task."""
    if today is None:
        today = datetime.now().date()

    processed: List[Dict[str, Any]] = []
    for task in tasks:
        normalised = dict(task)
        urgent = bool(normalised.get("urgent", False))
        important = bool(normalised.get("important", False))
        completion_rate = float(normalised.get("completion_rate", 0.0))
        completion_rate = max(0.0, min(1.0, completion_rate))
        normalised["completion_rate"] = completion_rate
        normalised["urgent"] = urgent
        normalised["important"] = important

        due_value = normalised.get("due_date")
        warning_text = None
        if urgent and not due_value:
            warning_text = "missing due date"
        elif due_value:
            try:
                due_dt = datetime.strptime(str(due_value), "%Y-%m-%d").date()
                days_left = (due_dt - today).days
                if due_dt < today:
                    overdue_days = (today - due_dt).days
                    warning_text = f"overdue by {overdue_days} day{'s' if overdue_days != 1 else ''}"
                elif not urgent and days_left <= 7:
                    warning_text = "due soon: consider marking urgent"
            except ValueError:
                pass

        normalised["warning"] = warning_text
        processed.append(normalised)

    return processed


def compute_risk(tasks: List[Dict[str, Any]]) -> Tuple[float, torch.Tensor, torch.Tensor]:
    """Evaluate the optimisation objective using PyTorch and backpropagate through completion rates."""
    c = torch.tensor([task["completion_rate"] for task in tasks], dtype=torch.float32, requires_grad=True)
    I = torch.tensor([1.0 if task.get("important", False) else 0.0 for task in tasks], dtype=torch.float32)
    U = torch.tensor([1.0 if task.get("urgent", False) else 0.0 for task in tasks], dtype=torch.float32)

    due_values: List[float] = []
    today = datetime.now().date()
    for task in tasks:
        due_value = task.get("due_date")
        if not due_value:
            due_values.append(float("inf"))
            continue
        try:
            due_dt = datetime.strptime(str(due_value), "%Y-%m-%d").date()
            due_values.append(float((due_dt - today).days))
        except ValueError:
            due_values.append(float("inf"))

    d = torch.tensor(due_values, dtype=torch.float32)
    d_positive = torch.clamp(d, min=0.0)

    urgency_contribution = U * (1.0 + 1.0 / (1.0 + d_positive))
    losses = (1.0 - c) ** 2 * (1.0 + I + urgency_contribution)
    R = losses.sum()
    R.backward()

    grad_R = c.grad.detach().clone()
    return float(R.item()), grad_R, c.detach()


def compute_allocation(grad_R: torch.Tensor) -> torch.Tensor:
    """Create the allocation vector from the gradient by following the requested normalisation."""
    l1_norm = torch.sum(torch.abs(grad_R))
    if l1_norm <= 0:
        return torch.zeros_like(grad_R)
    return (-grad_R) / l1_norm


def draw_theory_panel(ax: plt.Axes, tasks: List[Dict[str, Any]], risk_value: float) -> None:
    """Render the optimisation theory text as centered, loose text above the table."""
    title_y = 40
    line_gap = 35

    # ax.text(
    #     WIDTH / 2,
    #     title_y,
    #     "Theory",
    #     color=TEXT_COLOR,
    #     fontsize=14,
    #     fontweight="bold",
    #     family="DejaVu Sans",
    #     ha="center",
    #     va="center",
    # )
    ax.text(
        WIDTH / 2,
        title_y,
        r"GIVEN: No. of tasks $n$; Completion $c_i \in [0, 1]$, Urgency $U_i \in \{0, 1\}$, Importance $I_i \in \{0, 1\}$, Days to due date (else $\infty$) $d_i$",
        color=TEXT_COLOR,
        fontsize=14,
        family="DejaVu Sans",
        ha="center",
        va="center",
    )
    ax.text(
        WIDTH / 2,
        title_y + line_gap,
        r"DEFINE: Loss $\ell_i = (1-c_i)^2\left(1+I_i+U_i\left(1+\frac{1}{1+\max(d_i,0)}\right)\right)$, Risk $R(c_1, c_2, \ldots, c_n)=\sum_{i=1}^{n}\ell_i = %.3f$" % risk_value,
        color=TEXT_COLOR,
        fontsize=15,
        family="DejaVu Sans",
        ha="center",
        va="center",
    )
    ax.text(
        WIDTH / 2,
        title_y + 3 * line_gap,
        r"Recommended Resource Allocation % for task $i$ = $\frac{-\frac{\partial R}{\partial c_i}}{||\nabla R||_1}$",
        color=TEXT_COLOR,
        fontweight="bold",
        fontsize=20,
        family="DejaVu Sans",
        ha="center",
        va="center",
    )


def draw_quadrant(
    ax: plt.Axes,
    box: Tuple[float, float, float, float],
    title: str,
    entries: List[Tuple[Dict[str, Any], torch.Tensor]],
    global_max_abs_allocation: float,
) -> None:
    """Draw one quadrant of the Eisenhower matrix and the task rows inside it."""
    x0, y0, x1, y1 = box
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=(0.05, 0.05, 0.05), edgecolor=GRID_COLOR, linewidth=2))
    ax.text(x0 + 20, y0 + 36, title, color=TEXT_COLOR, fontsize=18, fontweight="bold", family="DejaVu Sans")

    header_y = y0 + 125
    ax.text(x0 + 40, header_y, "$c_i$", color=TEXT_COLOR, fontsize=18, family="DejaVu Sans")
    ax.text(
        x0 + 120,
        header_y,
        "$\\frac{-\\frac{\\partial R}{\\partial c_i}}{||\\nabla R||_1}$",
        color=TEXT_COLOR,
        fontsize=18,
        family="DejaVu Sans",
    )

    y_cursor = y0 + 175

    for task, allocation_value in entries:
        name = task.get("name", "Unnamed Task")
        completion_rate = task.get("completion_rate", 0.0)
        allocation_value = float(allocation_value)
        warning_text = task.get("warning")
        due_value = task.get("due_date")

        completion_text = f"{int(round(completion_rate * 100))}%"
        allocation_text = f"{int(round(abs(allocation_value) * 100))}%"

        box_size = 48
        completion_box = Rectangle((x0 + 40, y_cursor - 15), box_size, box_size, facecolor="none", edgecolor=GRID_COLOR, linewidth=1.5)
        allocation_box = Rectangle((x0 + 120, y_cursor - 15), box_size, box_size, facecolor="none", edgecolor=GRID_COLOR, linewidth=1.5)
        ax.add_patch(completion_box)
        ax.add_patch(allocation_box)

        cmap = plt.get_cmap(ALLOCATION_COLORMAP)
        normalized_value = allocation_value / global_max_abs_allocation if global_max_abs_allocation > 0 else 0.0
        fill_color = cmap(0.5 + 0.5 * normalized_value)
        allocation_fill = Rectangle((x0 + 120, y_cursor - 15), box_size, box_size, facecolor=fill_color, edgecolor=GRID_COLOR, linewidth=1.5)
        ax.add_patch(allocation_fill)

        ax.text(x0 + 40 + box_size / 2, y_cursor, completion_text, color=TEXT_COLOR, fontsize=11, ha="center", va="center", family="DejaVu Sans")
        ax.text(x0 + 120 + box_size / 2, y_cursor, allocation_text, color="black", fontsize=11, ha="center", va="center", family="DejaVu Sans")

        ax.text(x0 + 200, y_cursor, f"• {name}", color=TEXT_COLOR, fontsize=12, family="DejaVu Sans")

        if due_value:
            ax.text(x0 + 200, y_cursor + 20, f"Due: {due_value}", color=DUE_DATE_COLOR, fontsize=11, family="DejaVu Sans")
        if warning_text:
            ax.text(x0 + 200, y_cursor + 40, warning_text, color=WARN_COLOR, fontsize=11, family="DejaVu Sans")

        y_cursor += 70


def render_wallpaper(tasks: List[Dict[str, Any]], risk_value: float, allocation_values: torch.Tensor, timestamp: str) -> str:
    """Render the wallpaper as a matplotlib figure and save it to disk."""
    fig, ax = plt.subplots(figsize=(19.2, 10.8), dpi=100)
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)
    ax.set_xlim(0, WIDTH)
    ax.set_ylim(HEIGHT, 0)
    ax.axis("off")

    draw_theory_panel(ax, tasks, risk_value)

    box_w = int(WIDTH * TABLE_WIDTH_PERCENT)
    box_h = int(HEIGHT * TABLE_HEIGHT_PERCENT)
    x_min = (WIDTH - box_w) // 2
    x_max = x_min + box_w
    y_min = int(HEIGHT * 0.20)
    y_max = y_min + box_h
    x_mid = x_min + (box_w // 2)
    y_mid = y_min + (box_h // 2)

    ax.plot([x_mid, x_mid], [y_min, y_max], color=GRID_COLOR, linewidth=3)
    ax.plot([x_min, x_max], [y_mid, y_mid], color=GRID_COLOR, linewidth=3)
    ax.add_patch(Rectangle((x_min, y_min), box_w, box_h, fill=False, edgecolor=GRID_COLOR, linewidth=3))

    quadrants = {
        "Q1": {"title": "URGENT, IMPORTANT", "box": (x_mid, y_min, x_max, y_mid)},
        "Q2": {"title": "NOT URGENT, IMPORTANT", "box": (x_min, y_min, x_mid, y_mid)},
        "Q3": {"title": "URGENT, NOT IMPORTANT", "box": (x_mid, y_mid, x_max, y_max)},
        "Q4": {"title": "NOT URGENT, NOT IMPORTANT", "box": (x_min, y_mid, x_mid, y_max)},
    }

    bucketed = {"Q1": [], "Q2": [], "Q3": [], "Q4": []}

    for task, allocation_value in zip(tasks, allocation_values):
        is_urgent = task.get("urgent", False)
        is_important = task.get("important", False)

        if is_important and is_urgent:
            bucketed["Q1"].append((task, allocation_value))
        elif is_important:
            bucketed["Q2"].append((task, allocation_value))
        elif is_urgent:
            bucketed["Q3"].append((task, allocation_value))
        else:
            bucketed["Q4"].append((task, allocation_value))

    for q_id, entries in bucketed.items():
        if q_id in ["Q1", "Q3"]:
            entries.sort(key=lambda x: str(x[0].get("due_date", "9999-12-31")))
        else:
            entries.sort(key=lambda x: str(x[0].get("added_date", "1970-01-01")))

    global_max_abs_allocation = max(abs(float(value)) for _, value in [entry for entries in bucketed.values() for entry in entries]) if any(bucketed.values()) else 1e-6

    for q_id, info in quadrants.items():
        draw_quadrant(ax, info["box"], info["title"], bucketed[q_id], global_max_abs_allocation)

        ax.text(x_min + 20, y_max + 20, f"Last Update: {timestamp}", color=GRID_COLOR, fontsize=12, family="DejaVu Sans")
        ax.text(x_max - 20, y_max + 20, "github.com/ronitkunk/tasquick", color=GRID_COLOR, fontsize=12, ha="right", family="DejaVu Sans")

    clean_old_wallpapers()
    unique_filename = f"tasquick_{uuid.uuid4().hex}.png"
    output_path = os.path.join(WALLPAPER_DIR, unique_filename)
    fig.savefig(output_path, dpi=100, facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


def save_wallpaper(output_path: str) -> None:
    """Write the finished wallpaper to disk and apply it on macOS."""
    if os.path.exists(output_path):
        set_mac_wallpaper(output_path)


def watch_yaml() -> None:
    """Monitor the YAML file and regenerate the wallpaper when it changes."""
    print("Matrix Desktop Engine active. Monitoring tasks.yaml...")
    last_mtime = os.path.getmtime(YAML_PATH) if os.path.exists(YAML_PATH) else 0

    while True:
        try:
            if os.path.exists(YAML_PATH):
                current_mtime = os.path.getmtime(YAML_PATH)
                if current_mtime > last_mtime:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Change detected. Re-rendering matrix...")
                    main()
                    last_mtime = current_mtime
        except Exception as exc:
            print(f"Error encountered inside loop: {exc}")

        time.sleep(LOOP_INTERVAL_SECONDS)


def main() -> None:
    """Main entry point for one render pass."""
    tasks = preprocess_tasks(load_tasks())
    risk_value, grad_R, _ = compute_risk(tasks)
    allocation_values = compute_allocation(grad_R)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    output_path = render_wallpaper(tasks, risk_value, allocation_values, timestamp)
    save_wallpaper(output_path)


if __name__ == "__main__":
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Initializing desktop matrix...")
        main()
    except Exception as exc:
        print(f"Initial render failed: {exc}")

    watch_yaml()
