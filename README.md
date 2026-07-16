# tasquick

Upgrade your Mac wallpaper to an Eisenhower Matrix that auto-updates in real-time based on a list of your tasks, and use calculus to determine the ideal fraction of your resources to allocate to each task!

![tasquick banner](banner.png)

## Usage
- Clone this repo
```sh
git clone github.com/ronitkunk/tasquick
```
- Install dependencies
```sh
pip install pyyaml matplotlib torch
```
- Create a YAML containing your tasks anywhere on your computer
    - Recommended: pin the YAML to your dock for easy edit access, or make a shortcut to it
```yaml
- name: Call about new fridge
  important: true
  urgent: false
  added_date: 2026-07-15
  completion_rate: 0.0

- name: Track Roomba battery order
  important: true
  urgent: false
  added_date: 2026-07-15
  due_date: 2026-07-16
  completion_rate: 0.0

- name: Migrate/back up accounts on university email
  important: true
  urgent: true
  added_date: 2026-07-15
  due_date: 2026-07-15
  completion_rate: 0.0

- name: Web check-in
  important: true
  urgent: true
  added_date: 2026-07-14
  due_date: 2026-07-14
  completion_rate: 0.5

- name: Do laundry
  important: false
  urgent: true
  added_date: 2026-07-15
  due_date: 2026-07-15
  completion_rate: 0.0

- name: Water purifier shopping
  important: false
  urgent: false
  added_date: 2026-07-15
  completion_rate: 0.0
```

- From the repo root, run main.py on the YAML to begin wallpaper updates
    - It is recommended to run this in a `tmux` pane to prevent accidental termination
    - The display is refreshed approximately every 15 seconds by default. This can be configured using the macro `LOOP_INTERVAL_SECONDS` in `main.py`
    - Replace `PATH_TO_YOUR_YAML` with the path, for example, `python main.py tasks.yaml`
```sh
python main.py PATH_TO_YOUR_YAML
```

## Theory
The simple idea is to design a metric that penalises the non-completion of each task differently based on importance, urgency, due date, etc., and then ask: in what proportion should I increase completion rates of each task to reduce the risk most?

Formally, the optimisation problem is formulated as follows.

Given:
- No. of tasks $n$
- For each task $i \in \{1, 2, \ldots, n\}$:
  - Completion $c_i \in [0, 1]$
  - Difficulty $D_i \in \mathbb{R}^+$
  - Urgency $U_i \in \{0, 1\}$
  - Importance $I_i \in \{0, 1\}$
  - Days to due date $d_i$ (or $\infty$ if the due date is not defined)

We define:
- The loss $\ell_i$ of each task as $\ell_i = D_i^2(1-c_i)^2\left(1+I_i+U_i\left(1+\frac{1}{1+\max(d_i,0)}\right)\right)$
  - time to due date is only penalised if the task is urgent
  - if there is no due date, urgency is penalised with the same weight as importance
  - if there is a due date for an urgent task, the urgency penalty increases with closeness to the due date, maxxing out at twice the weight of importance
- The cumulative risk $R$ as $R(c_1, c_2, \ldots, c_n)=\sum_{i=1}^{n}\ell_i$
- The optimal direction to change $[c_1, c_2, \ldots, c_n]^\top$ is the direction of steepest descent of $R$, i.e., $-\nabla R$
  - Since $-\frac{\partial R}{\partial c_i}$ is nonnegative in this range, $\frac{-\frac{\partial R}{\partial c_i}}{||\nabla R||_1}$ is used as a proxy for the optimal fraction of resources that should be spent on task $i$.

## Implementation
The code in this repository was written with the assistance of LLMs. The use of PyTorch autograd to compute $\nabla R$ (instead of the closed form expression) is largely performative. However his also makes it easier to change the loss function without having to rewrite the gradient expression(s) by hand.

## Testing
It works for me. Use at your own risk.

## Contribution
Just make your own fork. See licence.