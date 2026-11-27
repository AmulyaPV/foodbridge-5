import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as patches

OUTPUT_DIR = "foodbridge-5/report_figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)

plt.rcParams['font.sans-serif'] = 'DejaVu Sans'

def save_fig(fig, filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    fig.savefig(filepath, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {filepath}")

# -------------------------------------------------------------
# Figure 3.2: Components of Result Processing (Smart Match & Safe-Until Processing)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 6))
ax.set_xlim(0, 10)
ax.set_ylim(0, 6)
ax.axis('off')

# Title
ax.text(5, 5.6, "Components of Result & Request Processing Engine", ha='center', va='center', fontsize=14, fontweight='bold', color='#1e3a2f')

# Main blocks
boxes = [
    (0.8, 3.8, 2.2, 1.0, "#e8f5e9", "#2e7d32", "1. Distance & Travel\nCalculation (Haversine/Maps)"),
    (3.9, 3.8, 2.2, 1.0, "#e8f5e9", "#2e7d32", "2. Safe-Until Clock\nValidator (Countdown)"),
    (7.0, 3.8, 2.2, 1.0, "#e8f5e9", "#2e7d32", "3. Smart Match Engine\n(Top 5 NGOs Ranking)"),
    (0.8, 1.8, 2.2, 1.0, "#e3f2fd", "#1565c0", "4. Transactional Locking\n(Select For Update)"),
    (3.9, 1.8, 2.2, 1.0, "#e3f2fd", "#1565c0", "5. 6-Digit Handover Code\nGenerator (SHA-256)"),
    (7.0, 1.8, 2.2, 1.0, "#fff3e0", "#e65100", "6. Impact & Reliability\nScore Aggregator")
]

for x, y, w, h, bg, border, text in boxes:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.1", ec=border, fc=bg, lw=1.8)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=9.5, fontweight='bold', color='#212121')

# Arrows connecting
arrow_style = dict(facecolor='#424242', edgecolor='#424242', width=1.5, headwidth=6, shrink=0.1)
ax.annotate('', xy=(3.9, 4.3), xytext=(3.0, 4.3), arrowprops=arrow_style)
ax.annotate('', xy=(7.0, 4.3), xytext=(6.1, 4.3), arrowprops=arrow_style)
ax.annotate('', xy=(5.0, 2.8), xytext=(5.0, 3.8), arrowprops=arrow_style)
ax.annotate('', xy=(3.0, 2.3), xytext=(3.9, 2.3), arrowprops=arrow_style)
ax.annotate('', xy=(7.0, 2.3), xytext=(6.1, 2.3), arrowprops=arrow_style)

# Bottom summary label
ax.text(5, 0.6, "Result: Reliable, Authenticated & Verified Food Redistribution Pipeline", ha='center', va='center', fontsize=11, fontstyle='italic', color='#424242')

save_fig(fig, "fig_3_2_result_processing_components.png")


# -------------------------------------------------------------
# Figure 3.3: Use Case Diagram of FoodBridge
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(11, 7.5))
ax.set_xlim(0, 11)
ax.set_ylim(0, 7.5)
ax.axis('off')

# Boundary box
sys_box = patches.FancyBboxPatch((3.0, 0.4), 5.0, 6.7, boxstyle="square,pad=0.1", ec="#37474f", fc="#fdfdfd", lw=2)
ax.add_patch(sys_box)
ax.text(5.5, 6.8, "FoodBridge Platform Boundary", ha='center', va='center', fontsize=12, fontweight='bold', color='#263238')

# Actors
actors = [
    (1.2, 5.8, "Hotel / Restaurant\n(Donor)"),
    (1.2, 3.5, "NGO / Individual\n(Recipient)"),
    (9.8, 3.8, "Administrator\n(System Authority)")
]

for x, y, name in actors:
    # simple stick figure representation
    circle = patches.Circle((x, y + 0.35), 0.22, ec='#1565c0', fc='#bbdefb', lw=1.8)
    ax.add_patch(circle)
    ax.plot([x, x], [y + 0.13, y - 0.3], color='#1565c0', lw=2)
    ax.plot([x - 0.25, x + 0.25], [y - 0.05, y - 0.05], color='#1565c0', lw=2)
    ax.plot([x, x - 0.2], [y - 0.3, y - 0.6], color='#1565c0', lw=2)
    ax.plot([x, x + 0.2], [y - 0.3, y - 0.6], color='#1565c0', lw=2)
    ax.text(x, y - 0.85, name, ha='center', va='top', fontsize=9.5, fontweight='bold')

# Use case ovals
use_cases = [
    (5.5, 6.2, "Post Surplus Food Listing"),
    (5.5, 5.3, "Browse & Distance Filtering"),
    (5.5, 4.4, "Request Food (Safe Clock Check)"),
    (5.5, 3.5, "Confirm & Reserve Servings"),
    (5.5, 2.6, "Handover Verification (6-digit Code)"),
    (5.5, 1.7, "Verification Queue & Moderation"),
    (5.5, 0.8, "Impact Certificate & Audit Reports")
]

for cx, cy, text in use_cases:
    ellipse = patches.Ellipse((cx, cy), 4.2, 0.65, ec='#2e7d32', fc='#f1f8e9', lw=1.5)
    ax.add_patch(ellipse)
    ax.text(cx, cy, text, ha='center', va='center', fontsize=9, fontweight='bold', color='#1b5e20')

# Connections from Hotel
for cy in [6.2, 3.5, 2.6, 0.8]:
    ax.plot([1.6, 3.4], [5.8, cy], color='#546e7a', lw=1.2, linestyle='-')

# Connections from Recipient
for cy in [5.3, 4.4, 2.6]:
    ax.plot([1.6, 3.4], [3.5, cy], color='#546e7a', lw=1.2, linestyle='-')

# Connections from Admin
for cy in [1.7, 0.8]:
    ax.plot([9.3, 7.6], [3.8, cy], color='#546e7a', lw=1.2, linestyle='-')

save_fig(fig, "fig_3_3_use_case_diagram.png")


# -------------------------------------------------------------
# Figure 3.4: Preprocessing Module (Data Validation, Sanitization, Geocoding)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5.5))
ax.set_xlim(0, 9)
ax.set_ylim(0, 5.5)
ax.axis('off')

ax.text(4.5, 5.1, "Preprocessing & Verification Pipeline", ha='center', va='center', fontsize=13, fontweight='bold', color='#1e3a2f')

steps_pre = [
    (0.6, 3.6, 2.2, 0.9, "User Input / Registration\n(Hotel / NGO / Individual)"),
    (3.4, 3.6, 2.2, 0.9, "Data Validation & Sanitization\n(FSSAI, Phone, File type)"),
    (6.2, 3.6, 2.2, 0.9, "Geocoding & Location\n(Coordinates & Area Tagging)"),
    (2.0, 1.8, 2.2, 0.9, "Admin Verification Queue\n(Pending -> Approved/Rejected)"),
    (5.0, 1.8, 2.4, 0.9, "Role-Based Profile Activation\n(Access Permission Granted)")
]

for x, y, w, h, text in steps_pre:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", ec="#00695c", fc="#e0f2f1", lw=1.6)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, fontweight='bold')

ax.annotate('', xy=(3.4, 4.05), xytext=(2.8, 4.05), arrowprops=dict(facecolor='#004d40', width=1.5, headwidth=6))
ax.annotate('', xy=(6.2, 4.05), xytext=(5.6, 4.05), arrowprops=dict(facecolor='#004d40', width=1.5, headwidth=6))
ax.annotate('', xy=(7.3, 2.7), xytext=(7.3, 3.6), arrowprops=dict(facecolor='#004d40', width=1.5, headwidth=6))
ax.annotate('', xy=(4.2, 2.25), xytext=(7.3, 2.25), arrowprops=dict(facecolor='#004d40', width=1.5, headwidth=6))
ax.annotate('', xy=(5.0, 2.25), xytext=(4.2, 2.25), arrowprops=dict(facecolor='#004d40', width=1.5, headwidth=6))

save_fig(fig, "fig_3_4_preprocessing_module.png")


# -------------------------------------------------------------
# Figure 3.5: Problem Solving Module (Safe-Until Clock & Smart Match Allocation)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9.5, 6))
ax.set_xlim(0, 9.5)
ax.set_ylim(0, 6)
ax.axis('off')

ax.text(4.75, 5.6, "Problem Solving: Surplus Allocation & Safe-Until Clock", ha='center', va='center', fontsize=13, fontweight='bold', color='#1e3a2f')

nodes = [
    (0.5, 3.8, 2.3, 1.0, "Hotel Posts Surplus Food\n(Listing + Safe-Until Time)"),
    (3.6, 3.8, 2.3, 1.0, "Smart Match Algorithm\n(Sort NGOs by Distance & Rating)"),
    (6.7, 3.8, 2.3, 1.0, "First-Look Window (10 min)\n(Top 5 Verified NGOs)"),
    (2.0, 1.8, 2.4, 1.0, "Recipient Request\n(ETA vs Safe-Until Check)"),
    (5.2, 1.8, 2.4, 1.0, "Atomic Reservation\n(Transactional Row Lock)")
]

for x, y, w, h, text in nodes:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", ec="#b71c1c", fc="#ffebee", lw=1.6)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, fontweight='bold')

ax.annotate('', xy=(3.6, 4.3), xytext=(2.8, 4.3), arrowprops=dict(facecolor='#b71c1c', width=1.5, headwidth=6))
ax.annotate('', xy=(6.7, 4.3), xytext=(5.9, 4.3), arrowprops=dict(facecolor='#b71c1c', width=1.5, headwidth=6))
ax.annotate('', xy=(7.8, 2.8), xytext=(7.8, 3.8), arrowprops=dict(facecolor='#b71c1c', width=1.5, headwidth=6))
ax.annotate('', xy=(4.4, 2.3), xytext=(7.8, 2.3), arrowprops=dict(facecolor='#b71c1c', width=1.5, headwidth=6))
ax.annotate('', xy=(5.2, 2.3), xytext=(4.4, 2.3), arrowprops=dict(facecolor='#b71c1c', width=1.5, headwidth=6))

save_fig(fig, "fig_3_5_problem_solving_module.png")


# -------------------------------------------------------------
# Figure 3.6: Progress Tracking Module (Handover Lifecycle & Security)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5))
ax.set_xlim(0, 10)
ax.set_ylim(0, 5)
ax.axis('off')

ax.text(5, 4.6, "Pickup Progress Tracking & Handover Security", ha='center', va='center', fontsize=13, fontweight='bold', color='#1e3a2f')

stages = [
    (0.5, 2.4, 1.6, 0.9, "1. Requested\n(By Recipient)"),
    (2.4, 2.4, 1.6, 0.9, "2. Confirmed\n(Code Issued)"),
    (4.3, 2.4, 1.6, 0.9, "3. On The Way\n(ETA Broadcast)"),
    (6.2, 2.4, 1.6, 0.9, "4. Verification\n(6-Digit Code)"),
    (8.1, 2.4, 1.6, 0.9, "5. Collected\n(Success & Logged)")
]

for x, y, w, h, text in stages:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", ec="#283593", fc="#e8eaf6", lw=1.6)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, fontweight='bold')

for i in range(len(stages) - 1):
    x1 = stages[i][0] + stages[i][2]
    x2 = stages[i+1][0]
    ax.annotate('', xy=(x2, 2.85), xytext=(x1, 2.85), arrowprops=dict(facecolor='#283593', width=1.5, headwidth=6))

# Sub-note on lockout
rect_note = patches.FancyBboxPatch((5.3, 0.8), 3.4, 0.8, boxstyle="round,pad=0.08", ec="#c62828", fc="#ffebee", lw=1.4)
ax.add_patch(rect_note)
ax.text(7.0, 1.2, "Security Guard: 5 wrong code attempts\nlock pickup -> Admin alert", ha='center', va='center', fontsize=8, color='#c62828', fontweight='bold')
ax.annotate('', xy=(7.0, 2.4), xytext=(7.0, 1.6), arrowprops=dict(facecolor='#c62828', width=1.2, headwidth=5))

save_fig(fig, "fig_3_6_progress_tracking_module.png")


# -------------------------------------------------------------
# Figure 3.7: Feedback and Analysis Module (Reports & Moderation)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9.5, 5))
ax.set_xlim(0, 9.5)
ax.set_ylim(0, 5)
ax.axis('off')

ax.text(4.75, 4.6, "Feedback, Moderation and Analysis Module", ha='center', va='center', fontsize=13, fontweight='bold', color='#1e3a2f')

boxes_fb = [
    (0.6, 2.3, 2.5, 1.1, "Listing Flagging / Report\n(Unsafe, Misleading, Other)"),
    (3.5, 2.3, 2.5, 1.1, "Admin Moderation Console\n(Remove / Dismiss / Suspend)"),
    (6.4, 2.3, 2.5, 1.1, "System Analytics & Reports\n(Servings, Waste Saved, CO2)")
]

for x, y, w, h, text in boxes_fb:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", ec="#ef6c00", fc="#fff3e0", lw=1.6)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, fontweight='bold')

ax.annotate('', xy=(3.5, 2.85), xytext=(3.1, 2.85), arrowprops=dict(facecolor='#e65100', width=1.5, headwidth=6))
ax.annotate('', xy=(6.4, 2.85), xytext=(6.0, 2.85), arrowprops=dict(facecolor='#e65100', width=1.5, headwidth=6))

save_fig(fig, "fig_3_7_feedback_and_analysis_module.png")


# -------------------------------------------------------------
# Figure 3.8: Community Interaction Module (NGO Needs Board)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9, 5))
ax.set_xlim(0, 9)
ax.set_ylim(0, 5)
ax.axis('off')

ax.text(4.5, 4.6, "Community Interaction Module: NGO Needs Board", ha='center', va='center', fontsize=13, fontweight='bold', color='#1e3a2f')

boxes_com = [
    (0.7, 2.2, 2.2, 1.2, "NGO Posts Requirement\n(e.g., 60 servings tonight)"),
    (3.4, 2.2, 2.2, 1.2, "Central Needs Board\n(Shared Community View)"),
    (6.1, 2.2, 2.2, 1.2, "Hotels View & Prioritize\n(Targeted Meal Donation)")
]

for x, y, w, h, text in boxes_com:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", ec="#4527a0", fc="#ede7f6", lw=1.6)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, fontweight='bold')

ax.annotate('', xy=(3.4, 2.8), xytext=(2.9, 2.8), arrowprops=dict(facecolor='#4527a0', width=1.5, headwidth=6))
ax.annotate('', xy=(6.1, 2.8), xytext=(5.6, 2.8), arrowprops=dict(facecolor='#4527a0', width=1.5, headwidth=6))

save_fig(fig, "fig_3_8_community_interaction_module.png")


# -------------------------------------------------------------
# Figure 3.9: Gamification Module (Impact Certificate & Reliability Score)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(9.5, 5))
ax.set_xlim(0, 9.5)
ax.set_ylim(0, 5)
ax.axis('off')

ax.text(4.75, 4.6, "Gamification & Trust Incentives (Badges & Impact)", ha='center', va='center', fontsize=13, fontweight='bold', color='#1e3a2f')

boxes_game = [
    (0.6, 2.2, 2.6, 1.2, "Completed Pickups Record\n(Verified Handover Log)"),
    (3.5, 2.2, 2.6, 1.2, "Reliability Score Engine\n(Collected vs Missed Score)"),
    (6.4, 2.2, 2.6, 1.2, "Impact Certificate & Badges\n(CO2 Saved, Meals Given)")
]

for x, y, w, h, text in boxes_game:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", ec="#2e7d32", fc="#e8f5e9", lw=1.6)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, fontweight='bold')

ax.annotate('', xy=(3.5, 2.8), xytext=(3.2, 2.8), arrowprops=dict(facecolor='#2e7d32', width=1.5, headwidth=6))
ax.annotate('', xy=(6.4, 2.8), xytext=(6.1, 2.8), arrowprops=dict(facecolor='#2e7d32', width=1.5, headwidth=6))

save_fig(fig, "fig_3_9_gamification_module.png")


# -------------------------------------------------------------
# Figure 3.10: Data Flow Diagram (DFD Level 0/1)
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 6.5))
ax.set_xlim(0, 10)
ax.set_ylim(0, 6.5)
ax.axis('off')

ax.text(5, 6.1, "Data Flow Diagram (Level 1) of FoodBridge System", ha='center', va='center', fontsize=13, fontweight='bold', color='#1e3a2f')

# External entities
ax.text(1.2, 4.5, "Hotel Entity", ha='center', va='center', bbox=dict(boxstyle="square,pad=0.3", fc="#cfd8dc", ec="#37474f", lw=1.5), fontweight='bold')
ax.text(1.2, 1.8, "Recipient Entity\n(NGO/Individual)", ha='center', va='center', bbox=dict(boxstyle="square,pad=0.3", fc="#cfd8dc", ec="#37474f", lw=1.5), fontweight='bold')
ax.text(8.8, 3.2, "Admin Entity", ha='center', va='center', bbox=dict(boxstyle="square,pad=0.3", fc="#cfd8dc", ec="#37474f", lw=1.5), fontweight='bold')

# Core process circle
circle_proc = patches.Circle((5.0, 3.2), 1.3, ec='#0277bd', fc='#e1f5fe', lw=2)
ax.add_patch(circle_proc)
ax.text(5.0, 3.2, "FoodBridge\nCore Processing\nEngine (1.0)", ha='center', va='center', fontsize=9.5, fontweight='bold', color='#01579b')

# Arrows
ax.annotate('1. Post Surplus', xy=(3.7, 3.8), xytext=(2.0, 4.5), arrowprops=dict(facecolor='#37474f', width=1.2, headwidth=5))
ax.annotate('2. Request Servings', xy=(3.7, 2.6), xytext=(2.0, 1.8), arrowprops=dict(facecolor='#37474f', width=1.2, headwidth=5))
ax.annotate('3. Handover Code Check', xy=(2.0, 4.1), xytext=(3.7, 3.4), arrowprops=dict(facecolor='#37474f', width=1.2, headwidth=5))
ax.annotate('4. Verification & Audit', xy=(6.3, 3.2), xytext=(8.0, 3.2), arrowprops=dict(facecolor='#37474f', width=1.2, headwidth=5))

# Data store
ax.plot([4.0, 6.0], [0.8, 0.8], color='#2e7d32', lw=2)
ax.plot([4.0, 6.0], [1.3, 1.3], color='#2e7d32', lw=2)
ax.text(5.0, 1.05, "D1: SQLite Database (db.sqlite3)", ha='center', va='center', fontsize=9, fontweight='bold', color='#1b5e20')
ax.annotate('', xy=(5.0, 1.3), xytext=(5.0, 1.9), arrowprops=dict(facecolor='#2e7d32', width=1.2, headwidth=5))

save_fig(fig, "fig_3_10_data_flow_diagram.png")


# -------------------------------------------------------------
# Figure 3.11: Data Flow Diagram of Classification / Matching Module
# -------------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 5.5))
ax.set_xlim(0, 10)
ax.set_ylim(0, 5.5)
ax.axis('off')

ax.text(5, 5.1, "DFD of Classification & Smart Match Module", ha='center', va='center', fontsize=13, fontweight='bold', color='#1e3a2f')

dfd_steps = [
    (0.6, 2.4, 2.0, 1.1, "New Food Listing\n(Veg / Non-Veg / Vegan)"),
    (3.0, 2.4, 2.2, 1.1, "Category & Geo Filter\n(Radius & Safe-Clock)"),
    (5.6, 2.4, 2.2, 1.1, "Reliability Ranker\n(Smart Match Scoring)"),
    (8.2, 2.4, 1.5, 1.1, "Top 5 Match\nBroadcast")
]

for x, y, w, h, text in dfd_steps:
    rect = patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08", ec="#00838f", fc="#e0f7fa", lw=1.6)
    ax.add_patch(rect)
    ax.text(x + w/2, y + h/2, text, ha='center', va='center', fontsize=8.5, fontweight='bold')

for i in range(len(dfd_steps) - 1):
    x1 = dfd_steps[i][0] + dfd_steps[i][2]
    x2 = dfd_steps[i+1][0]
    ax.annotate('', xy=(x2, 2.95), xytext=(x1, 2.95), arrowprops=dict(facecolor='#00838f', width=1.5, headwidth=6))

save_fig(fig, "fig_3_11_dfd_classification_module.png")

print("All 10 diagrams successfully generated!")
