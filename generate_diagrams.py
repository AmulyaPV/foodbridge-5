import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

OUTPUT_DIR = "docs/report_figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)

plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['font.family'] = 'sans-serif'

def save_fig(fig, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    fig.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white', edgecolor='none')
    plt.close(fig)
    print(f"Generated clean figure: {filepath}")

DARK_GREEN = "#183b2b"
BORDER_DARK = "#2d5a3f"
TEXT_COLOR = "#1a2e22"
ARROW_COLOR = "#2d5a3f"

# =============================================================================
# Figure 3.2: Components of Result & Request Processing Engine
# =============================================================================
fig, ax = plt.subplots(figsize=(10, 6.2))
ax.set_xlim(0, 10)
ax.set_ylim(0, 6.2)
ax.axis('off')

# Title & Subtitle
ax.text(5, 5.8, "Components of Result & Request Processing Engine", ha='center', va='center', fontsize=15, fontweight='bold', color=DARK_GREEN)

boxes_3_2 = [
    (0.8, 3.8, 2.5, 1.25, "#eef6f0", "#2d7a4f", "1. Distance & Travel\nCalculation\n(Haversine / Routes API)"),
    (3.75, 3.8, 2.5, 1.25, "#eef6f0", "#2d7a4f", "2. Safe-Until Clock\nValidator\n(Dynamic Countdown)"),
    (6.7, 3.8, 2.5, 1.25, "#eef6f0", "#2d7a4f", "3. Smart Match Engine\n(Top 5 Ranked NGOs\n10-Min First Look)"),
    (0.8, 1.7, 2.5, 1.25, "#e8f2fc", "#1976d2", "4. Transactional Locking\n(select_for_update\nRow Locks)"),
    (3.75, 1.7, 2.5, 1.25, "#e8f2fc", "#1976d2", "5. 6-Digit Handover Code\nGenerator\n(SHA-256 Hash + Salt)"),
    (6.7, 1.7, 2.5, 1.25, "#fff4e5", "#e65100", "6. Impact & Reliability\nScore Aggregator\n(Verified Ledger)")
]

for x, y, w, h, bg, border, text in boxes_3_2:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.12", ec=border, fc=bg, lw=2.0)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=9.5, fontweight='bold', color=TEXT_COLOR, linespacing=1.25)

# Connectors
arrow = dict(facecolor='#37474f', edgecolor='#37474f', width=1.8, headwidth=7, headlength=7, shrink=0.08)
ax.annotate('', xy=(3.75, 4.42), xytext=(3.3, 4.42), arrowprops=arrow)
ax.annotate('', xy=(6.7, 4.42), xytext=(6.25, 4.42), arrowprops=arrow)
ax.annotate('', xy=(5.0, 2.95), xytext=(5.0, 3.8), arrowprops=arrow)
ax.annotate('', xy=(3.3, 2.32), xytext=(3.75, 2.32), arrowprops=arrow)
ax.annotate('', xy=(6.7, 2.32), xytext=(6.25, 2.32), arrowprops=arrow)

ax.text(5, 0.65, "Result: Reliable, Authenticated & Verified Food Redistribution Pipeline", ha='center', va='center', fontsize=11, fontstyle='italic', color='#52685c')
save_fig(fig, "fig_3_2_result_processing_components.png")


# =============================================================================
# Figure 3.3: Use Case Diagram of FoodBridge Actors
# =============================================================================
fig, ax = plt.subplots(figsize=(11, 7.8))
ax.set_xlim(0, 11)
ax.set_ylim(0, 7.8)
ax.axis('off')

# Boundary box
sys_box = patches.FancyBboxPatch((3.0, 0.4), 5.0, 6.9, boxstyle="square,pad=0.1", ec="#37474f", fc="#fafafa", lw=2)
ax.add_patch(sys_box)
ax.text(5.5, 7.0, "FoodBridge Platform Boundary", ha='center', va='center', fontsize=12.5, fontweight='bold', color=DARK_GREEN)

# Actors (Hotel, Recipient, Admin)
actors = [
    (1.2, 5.8, "Hotel / Restaurant\n(Food Donor)"),
    (1.2, 3.5, "NGO / Individual\n(Recipient)"),
    (9.8, 3.7, "Administrator\n(System Authority)")
]

for x, y, name in actors:
    circle = patches.Circle((x, y + 0.35), 0.22, ec='#1976d2', fc='#e3f2fd', lw=1.8)
    ax.add_patch(circle)
    ax.plot([x, x], [y + 0.13, y - 0.3], color='#1976d2', lw=2)
    ax.plot([x - 0.25, x + 0.25], [y - 0.05, y - 0.05], color='#1976d2', lw=2)
    ax.plot([x, x - 0.2], [y - 0.3, y - 0.6], color='#1976d2', lw=2)
    ax.plot([x, x + 0.2], [y - 0.3, y - 0.6], color='#1976d2', lw=2)
    ax.text(x, y - 0.85, name, ha='center', va='top', fontsize=9.5, fontweight='bold', color=TEXT_COLOR)

use_cases = [
    (5.5, 6.35, "Post Surplus Food Listing & Items"),
    (5.5, 5.45, "Browse Nearby Food & Filter by Distance"),
    (5.5, 4.55, "Request Food (Safe Clock Feasibility Check)"),
    (5.5, 3.65, "Review & Approve / Partial Quantity Proposal"),
    (5.5, 2.75, "Verify Handover with 6-Digit Code"),
    (5.5, 1.85, "Review Account Verification & Moderation"),
    (5.5, 0.95, "Print Impact Certificate & Audit Reports")
]

for cx, cy, text in use_cases:
    ellipse = patches.Ellipse((cx, cy), 4.3, 0.65, ec='#2d7a4f', fc='#eef6f0', lw=1.6)
    ax.add_patch(ellipse)
    ax.text(cx, cy, text, ha='center', va='center', fontsize=8.8, fontweight='bold', color=DARK_GREEN)

# Hotel links
for cy in [6.35, 3.65, 2.75, 0.95]:
    ax.plot([1.6, 3.35], [5.8, cy], color='#546e7a', lw=1.3)

# Recipient links
for cy in [5.45, 4.55, 3.65, 2.75]:
    ax.plot([1.6, 3.35], [3.5, cy], color='#546e7a', lw=1.3)

# Admin links
for cy in [1.85, 0.95]:
    ax.plot([9.3, 7.65], [3.7, cy], color='#546e7a', lw=1.3)

save_fig(fig, "fig_3_3_use_case_diagram.png")


# =============================================================================
# Figure 3.4: Preprocessing Module (Data Validation, Sanitization, Geocoding)
# =============================================================================
fig, ax = plt.subplots(figsize=(9.5, 5.5))
ax.set_xlim(0, 9.5)
ax.set_ylim(0, 5.5)
ax.axis('off')

ax.text(4.75, 5.1, "Preprocessing & Account Verification Pipeline", ha='center', va='center', fontsize=14, fontweight='bold', color=DARK_GREEN)

steps_pre = [
    (0.6, 3.5, 2.4, 1.0, "1. User Registration\n(Hotel / NGO / Individual)"),
    (3.55, 3.5, 2.4, 1.0, "2. Data Sanitization\n(FSSAI, Phone, Certificate)"),
    (6.5, 3.5, 2.4, 1.0, "3. Geocoding Validation\n(Coordinates & Address Pin)"),
    (2.1, 1.6, 2.4, 1.0, "4. Admin Verification Queue\n(Pending -> Verified/Rejected)"),
    (5.1, 1.6, 2.4, 1.0, "5. Profile Activation\n(Role Permissions Granted)")
]

for x, y, w, h, text in steps_pre:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", ec="#00796b", fc="#e0f2f1", lw=1.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=9, fontweight='bold', color=TEXT_COLOR)

ax.annotate('', xy=(3.55, 4.0), xytext=(3.0, 4.0), arrowprops=arrow)
ax.annotate('', xy=(6.5, 4.0), xytext=(5.95, 4.0), arrowprops=arrow)
ax.annotate('', xy=(7.7, 2.6), xytext=(7.7, 3.5), arrowprops=arrow)
ax.annotate('', xy=(4.5, 2.1), xytext=(7.7, 2.1), arrowprops=arrow)
ax.annotate('', xy=(5.1, 2.1), xytext=(4.5, 2.1), arrowprops=arrow)

save_fig(fig, "fig_3_4_preprocessing_module.png")


# =============================================================================
# Figure 3.5: Problem Solving Module (Safe-Until Clock & Smart Match Allocation)
# =============================================================================
fig, ax = plt.subplots(figsize=(10, 5.8))
ax.set_xlim(0, 10)
ax.set_ylim(0, 5.8)
ax.axis('off')

ax.text(5, 5.4, "Problem Solving: Surplus Allocation & Safe-Until Clock", ha='center', va='center', fontsize=14, fontweight='bold', color=DARK_GREEN)

nodes_3_5 = [
    (0.6, 3.6, 2.5, 1.05, "1. Surplus Listing Posted\n(Multiple Items + Safe-Until)"),
    (3.75, 3.6, 2.5, 1.05, "2. Smart Match Ranking\n(Distance, Capacity, Rating)"),
    (6.9, 3.6, 2.5, 1.05, "3. 10-Min First Look\n(Broadcast to Top 5 NGOs)"),
    (2.15, 1.6, 2.5, 1.05, "4. Feasibility Check\n(ETA must be <= Safe-Until)"),
    (5.3, 1.6, 2.5, 1.05, "5. Atomic Stock Allocation\n(select_for_update Row Lock)")
]

for x, y, w, h, text in nodes_3_5:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", ec="#c62828", fc="#ffebee", lw=1.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=9, fontweight='bold', color=TEXT_COLOR)

ax.annotate('', xy=(3.75, 4.12), xytext=(3.1, 4.12), arrowprops=arrow)
ax.annotate('', xy=(6.9, 4.12), xytext=(6.25, 4.12), arrowprops=arrow)
ax.annotate('', xy=(8.15, 2.65), xytext=(8.15, 3.6), arrowprops=arrow)
ax.annotate('', xy=(4.65, 2.12), xytext=(8.15, 2.12), arrowprops=arrow)
ax.annotate('', xy=(5.3, 2.12), xytext=(4.65, 2.12), arrowprops=arrow)

save_fig(fig, "fig_3_5_problem_solving_module.png")


# =============================================================================
# Figure 3.6: Progress Tracking Module (Handover Lifecycle & Security)
# =============================================================================
fig, ax = plt.subplots(figsize=(10.5, 5.2))
ax.set_xlim(0, 10.5)
ax.set_ylim(0, 5.2)
ax.axis('off')

ax.text(5.25, 4.8, "Pickup Progress Tracking & Handover Security Lifecycle", ha='center', va='center', fontsize=14, fontweight='bold', color=DARK_GREEN)

stages = [
    (0.5, 2.5, 1.7, 1.0, "1. Requested\n(Items & Qty)"),
    (2.5, 2.5, 1.7, 1.0, "2. Confirmed\n(Code Generated)"),
    (4.5, 2.5, 1.7, 1.0, "3. On The Way\n(Live GPS ETA)"),
    (6.5, 2.5, 1.7, 1.0, "4. Verification\n(6-Digit Match)"),
    (8.5, 2.5, 1.7, 1.0, "5. Collected\n(Stock Cleared)")
]

for x, y, w, h, text in stages:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", ec="#283593", fc="#e8eaf6", lw=1.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.8, fontweight='bold', color=TEXT_COLOR)

for i in range(len(stages) - 1):
    x1 = stages[i][0] + stages[i][2]
    x2 = stages[i+1][0]
    ax.annotate('', xy=(x2, 3.0), xytext=(x1, 3.0), arrowprops=arrow)

# Security Callout
lockout_box = patches.FancyBboxPatch((5.5, 0.8), 3.8, 0.85, boxstyle="round,pad=0.08", ec="#b71c1c", fc="#ffebee", lw=1.5)
ax.add_patch(lockout_box)
ax.text(7.4, 1.22, "Security Guard: 5 wrong code attempts\nautomatically locks pickup -> Admin notification", ha='center', va='center', fontsize=8.2, fontweight='bold', color='#b71c1c')
ax.annotate('', xy=(7.35, 2.5), xytext=(7.4, 1.65), arrowprops=dict(facecolor='#b71c1c', edgecolor='#b71c1c', width=1.5, headwidth=6, shrink=0.08))

save_fig(fig, "fig_3_6_progress_tracking_module.png")


# =============================================================================
# Figure 3.7: Feedback, Moderation and Analysis Module
# =============================================================================
fig, ax = plt.subplots(figsize=(9.8, 5.2))
ax.set_xlim(0, 9.8)
ax.set_ylim(0, 5.2)
ax.axis('off')

ax.text(4.9, 4.8, "Feedback, Moderation and Quality Analysis Module", ha='center', va='center', fontsize=14, fontweight='bold', color=DARK_GREEN)

boxes_fb = [
    (0.6, 2.2, 2.6, 1.2, "1. Listing Flagging / Report\n(Unsafe, Misleading, Inappropriate)"),
    (3.6, 2.2, 2.6, 1.2, "2. Admin Moderation Console\n(Remove / Dismiss / Suspend Account)"),
    (6.6, 2.2, 2.6, 1.2, "3. Platform Analytics\n(Servings Saved, CO2 Reduction, Trends)")
]

for x, y, w, h, text in boxes_fb:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", ec="#e65100", fc="#fff3e0", lw=1.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.8, fontweight='bold', color=TEXT_COLOR)

ax.annotate('', xy=(3.6, 2.8), xytext=(3.2, 2.8), arrowprops=arrow)
ax.annotate('', xy=(6.6, 2.8), xytext=(6.2, 2.8), arrowprops=arrow)

save_fig(fig, "fig_3_7_feedback_and_analysis_module.png")


# =============================================================================
# Figure 3.8: Community Interaction Module (NGO Needs Board & Messaging)
# =============================================================================
fig, ax = plt.subplots(figsize=(9.8, 5.2))
ax.set_xlim(0, 9.8)
ax.set_ylim(0, 5.2)
ax.axis('off')

ax.text(4.9, 4.8, "Community Interaction Module: Needs Board & In-App Chat", ha='center', va='center', fontsize=14, fontweight='bold', color=DARK_GREEN)

boxes_com = [
    (0.6, 2.2, 2.6, 1.2, "1. NGO Posts Requirement\n(e.g., 80 meal servings tonight)"),
    (3.6, 2.2, 2.6, 1.2, "2. Community Needs Board\n(Shared Live Demand Board)"),
    (6.6, 2.2, 2.6, 1.2, "3. Donors Contact & Fulfill\n(Targeted Meal Delivery & Messaging)")
]

for x, y, w, h, text in boxes_com:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", ec="#4a148c", fc="#f3e5f5", lw=1.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.8, fontweight='bold', color=TEXT_COLOR)

ax.annotate('', xy=(3.6, 2.8), xytext=(3.2, 2.8), arrowprops=arrow)
ax.annotate('', xy=(6.6, 2.8), xytext=(6.2, 2.8), arrowprops=arrow)

save_fig(fig, "fig_3_8_community_interaction_module.png")


# =============================================================================
# Figure 3.9: Gamification Module (Impact Certificate & Reliability Score)
# =============================================================================
fig, ax = plt.subplots(figsize=(9.8, 5.2))
ax.set_xlim(0, 9.8)
ax.set_ylim(0, 5.2)
ax.axis('off')

ax.text(4.9, 4.8, "Gamification & Trust Incentives (Badges & Impact Certificate)", ha='center', va='center', fontsize=14, fontweight='bold', color=DARK_GREEN)

boxes_game = [
    (0.6, 2.2, 2.6, 1.2, "1. Verified Pickup Records\n(Audit Log of Completed Donations)"),
    (3.6, 2.2, 2.6, 1.2, "2. Reliability Score Engine\n(Collected vs Missed Percentage)"),
    (6.6, 2.2, 2.6, 1.2, "3. Impact Certificate & Badges\n(Printable PDF / CO2 Equivalents)")
]

for x, y, w, h, text in boxes_game:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", ec="#1b5e20", fc="#e8f5e9", lw=1.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.8, fontweight='bold', color=TEXT_COLOR)

ax.annotate('', xy=(3.6, 2.8), xytext=(3.2, 2.8), arrowprops=arrow)
ax.annotate('', xy=(6.6, 2.8), xytext=(6.2, 2.8), arrowprops=arrow)

save_fig(fig, "fig_3_9_gamification_module.png")


# =============================================================================
# Figure 3.10: Data Flow Diagram (Level 1) of FoodBridge System
# =============================================================================
fig, ax = plt.subplots(figsize=(10.5, 6.5))
ax.set_xlim(0, 10.5)
ax.set_ylim(0, 6.5)
ax.axis('off')

ax.text(5.25, 6.1, "Data Flow Diagram (Level 1) of FoodBridge System", ha='center', va='center', fontsize=14, fontweight='bold', color=DARK_GREEN)

# External entities
ax.text(1.3, 4.6, "Hotel / Donor\nEntity", ha='center', va='center', bbox=dict(boxstyle="square,pad=0.5", fc="#cfd8dc", ec="#37474f", lw=1.8), fontweight='bold', color=TEXT_COLOR)
ax.text(1.3, 1.8, "Recipient Entity\n(NGO / Individual)", ha='center', va='center', bbox=dict(boxstyle="square,pad=0.5", fc="#cfd8dc", ec="#37474f", lw=1.8), fontweight='bold', color=TEXT_COLOR)
ax.text(9.2, 3.2, "Administrator\nEntity", ha='center', va='center', bbox=dict(boxstyle="square,pad=0.5", fc="#cfd8dc", ec="#37474f", lw=1.8), fontweight='bold', color=TEXT_COLOR)

# Center Process Circle
circle_proc = patches.Circle((5.25, 3.2), 1.35, ec='#0277bd', fc='#e1f5fe', lw=2.2)
ax.add_patch(circle_proc)
ax.text(5.25, 3.5, "1.0", ha='center', va='center', fontsize=11, fontweight='bold', color='#01579b')
ax.text(5.25, 3.2, "FoodBridge Core", ha='center', va='center', fontsize=10.5, fontweight='bold', color='#01579b')
ax.text(5.25, 2.85, "Processing Engine", ha='center', va='center', fontsize=9, fontstyle='italic', color='#01579b')

# Arrows
ax.annotate('1. Post Surplus Listing', xy=(3.9, 3.8), xytext=(2.2, 4.6), arrowprops=dict(facecolor='#37474f', edgecolor='#37474f', width=1.5, headwidth=6, shrink=0.08), fontsize=8.5, fontweight='bold')
ax.annotate('2. Request Servings', xy=(3.9, 2.6), xytext=(2.3, 1.8), arrowprops=dict(facecolor='#37474f', edgecolor='#37474f', width=1.5, headwidth=6, shrink=0.08), fontsize=8.5, fontweight='bold')
ax.annotate('3. Handover Verification', xy=(2.3, 4.1), xytext=(3.9, 3.3), arrowprops=dict(facecolor='#37474f', edgecolor='#37474f', width=1.5, headwidth=6, shrink=0.08), fontsize=8.5, fontweight='bold')
ax.annotate('4. Verification & Audit', xy=(6.6, 3.2), xytext=(8.3, 3.2), arrowprops=dict(facecolor='#37474f', edgecolor='#37474f', width=1.5, headwidth=6, shrink=0.08), fontsize=8.5, fontweight='bold')

# Data store
ax.plot([4.2, 6.3], [0.8, 0.8], color='#2e7d32', lw=2.5)
ax.plot([4.2, 6.3], [1.35, 1.35], color='#2e7d32', lw=2.5)
ax.text(5.25, 1.08, "D1: SQLite Database (db.sqlite3)", ha='center', va='center', fontsize=9.2, fontweight='bold', color='#1b5e20')
ax.annotate('', xy=(5.25, 1.35), xytext=(5.25, 1.85), arrowprops=dict(facecolor='#2e7d32', edgecolor='#2e7d32', width=1.5, headwidth=6, shrink=0.08))
ax.text(6.05, 1.55, "Read / Write", ha='center', va='center', fontsize=8, fontstyle='italic', color='#2e7d32')

save_fig(fig, "fig_3_10_data_flow_diagram.png")


# =============================================================================
# Figure 3.11: Data Flow Diagram of Classification / Matching Module
# =============================================================================
fig, ax = plt.subplots(figsize=(10.5, 5.5))
ax.set_xlim(0, 10.5)
ax.set_ylim(0, 5.5)
ax.axis('off')

ax.text(5.25, 5.0, "DFD of Classification & Smart Match Module", ha='center', va='center', fontsize=14, fontweight='bold', color=DARK_GREEN)

dfd_steps = [
    (0.6, 2.3, 2.1, 1.2, "1. Surplus Listing\n(Veg / Non-Veg / Vegan\nFood Category & Servings)"),
    (3.1, 2.3, 2.2, 1.2, "2. Category & Geo Filter\n(Radius Haversine &\nSafe-Clock Feasibility)"),
    (5.7, 2.3, 2.2, 1.2, "3. Reliability Ranker\n(Smart Match Score &\nCapacity Matching)"),
    (8.3, 2.3, 1.6, 1.2, "4. First-Look\nTop 5 NGO\nBroadcast")
]

for x, y, w, h, text in dfd_steps:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", ec="#00838f", fc="#e0f7fa", lw=1.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, fontweight='bold', color=TEXT_COLOR)

for i in range(len(dfd_steps) - 1):
    x1 = dfd_steps[i][0] + dfd_steps[i][2]
    x2 = dfd_steps[i+1][0]
    ax.annotate('', xy=(x2, 2.9), xytext=(x1, 2.9), arrowprops=arrow)

save_fig(fig, "fig_3_11_dfd_classification_module.png")

print("All academic report diagrams regenerated with ultra-clean styling!")
