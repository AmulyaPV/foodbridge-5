import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUTPUT_DIR = os.path.abspath("report_figures")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def render_table_image(title, headers, data, filename, col_widths=None):
    fig, ax = plt.subplots(figsize=(12, len(data) * 0.45 + 1.6))
    ax.axis('off')
    
    plt.title(title, fontsize=13, weight='bold', pad=15, color='#1e3a2f')
    
    table = ax.table(
        cellText=data,
        colLabels=headers,
        cellLoc='left',
        loc='center',
        colWidths=col_widths
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9.5)
    table.scale(1.0, 1.6)
    
    # Style header
    for k, cell in table.get_celld().items():
        if k[0] == 0:
            cell.set_facecolor('#2e7d32')
            cell.set_text_props(color='white', weight='bold')
        else:
            if k[0] % 2 == 0:
                cell.set_facecolor('#f9fbe7')
            else:
                cell.set_facecolor('#ffffff')
            cell.set_edgecolor('#cfd8dc')
            
    fig.savefig(os.path.join(OUTPUT_DIR, filename), dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Saved {filename}")

# 1. Accounts Users Table Image (Figure for Database)
headers_user = ["ID", "Email Address", "Role", "Verification Status", "Is Staff / Superuser"]
data_user = [
    ["1", "admin@foodbridge.com", "admin", "Approved", "Yes (Admin Console Access)"],
    ["2", "baahotel@gmail.com", "hotel", "Approved", "No"],
    ["3", "ngo@gmail.com", "ngo", "Approved", "No"],
    ["4", "ngoamul@gmail.com", "ngo", "Approved", "No"],
    ["5", "grandpalace@demo.com", "hotel", "Approved", "No"],
    ["6", "tajgateway@demo.com", "hotel", "Approved", "No"],
    ["7", "spicekitchen@demo.com", "hotel", "Approved", "No"],
    ["8", "orientalwok@demo.com", "hotel", "Approved", "No"],
    ["9", "annaseva@demo.com", "ngo", "Approved", "No"],
    ["10", "feedthehungry@demo.com", "ngo", "Approved", "No"],
    ["11", "hopekitchen@demo.com", "ngo", "Approved", "No"],
    ["12", "carefoundation@demo.com", "ngo", "Approved", "No"],
    ["13", "anand.sharma@demo.com", "individual", "Approved", "No"],
    ["14", "fatima.begum@demo.com", "individual", "Approved", "No"],
    ["15", "mariamm@demo.com", "individual", "Approved", "No"]
]
render_table_image("FoodBridge Database Snapshot: accounts_user Table (15 Populated Accounts)", 
                   headers_user, data_user, "db_screenshot_accounts_user.png", [0.06, 0.32, 0.16, 0.22, 0.24])

# 2. Food Listings Table Image
headers_listing = ["ID", "Food Title", "Servings Available", "Total Servings", "Status", "Safe-Until Window"]
data_listing = [
    ["1", "Fresh Paneer Butter Masala, Dal & Roti", "60", "60", "Posted (Available)", "+5.0 Hours Remaining"],
    ["2", "Vegetable Pulao & Mixed Veg Curry", "45", "45", "Posted (Available)", "+4.0 Hours Remaining"],
    ["3", "South Indian Meals (Sambar, Rice)", "80", "80", "Posted (Available)", "+3.0 Hours Remaining"],
    ["4", "Buffet Boxes (Fried Rice, Sandwiches)", "35", "35", "Posted (Available)", "+6.0 Hours Remaining"]
]
render_table_image("FoodBridge Database Snapshot: core_foodlisting Table", 
                   headers_listing, data_listing, "db_screenshot_foodlistings.png", [0.06, 0.40, 0.16, 0.14, 0.16, 0.18])
