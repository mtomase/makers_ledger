### Manage Ingredients
*Purpose: This section is for tracking all your raw materials, their purchase costs, and suppliers. This data is the absolute foundation for calculating the material costs that go into each of your products.*

*Concept: Ingredients are the direct physical components of your products. To accurately determine how much it costs to make a product, you first need to know the precise cost of each inventory item per standardized unit (e.g., cost per gram or per kilogram). This allows for consistent costing even if you buy inventoryitems in various bulk sizes.*

**How to Use:**
- The table displays your current list of inventoryitems.
- **To Add a New Ingredient:** Click the `+ Add row` button at the bottom of the data editor. A new, empty row will appear for you to fill in.
- **To Edit an Existing Ingredient:** Simply click directly into any cell of an existing inventoryitem's row and modify its value.
- **To Delete an Ingredient:** Click the trash can icon (`🗑️`) located at the end of the row you wish to remove.
- **Important:** After making any changes, you **MUST** click the **"Save Inventory Item Changes"** button located below the table to make your modifications permanent.

**Key Fields & Concepts:**
- `Ingredient Name*`: A clear, descriptive name for the raw material (e.g., "Organic Cocoa Butter"). *Required.*
- `Provider (Optional)`: The supplier or source of the inventoryitem.
- `Price per Unit (€)*`: The price you pay for a specific quantity of the inventory item (e.g., €10 for a 5kg bag). *Required.*
- `Unit Quantity (kg)*`: The amount, **in kilograms**, that the `Price per Unit` refers to. This is crucial for standardizing costs.
    - *Example 1:* If you buy a 5kg bag of flour for €10, enter `5.000` here.
    - *Example 2:* If you buy a 250g jar of spice for €3, you would enter `0.250` here.
    - The app uses these two fields to calculate a standardized cost per kilogram: `Cost per kg = Price per Unit (€) / Unit Quantity (kg)`. *Required.*
- `Price URL (Optional)`: A web link for your reference.

*Significance: The data entered here directly feeds into the "Total Material Cost/Item" in the Product Cost Breakdown.*

---
### Manage Employees
*Purpose: This section allows you to list your employees and define their labor rates or note if they are salaried.*

*Concept: Labor is a significant cost. It's important to differentiate between **Direct Labor** (work directly attributable to making a product, costed via an hourly rate) and **Indirect Labor/Salaried Staff** (work supporting the business overall, treated as an overhead).*

**How to Use:**
- Add, edit, or delete employee records in the data editor.
- Always click **"Save Employee Changes"**.

**Key Fields & Concepts:**
- `Employee Name*`: Full name. *Required.*
- `Hourly Rate (€)*`: The labor cost of this employee per hour. This is crucial for employees whose time is tracked for specific tasks. For salaried employees whose cost is allocated as an overhead, you can enter `0.00`. *Required.*
- `Role (Optional)`: The employee's job title.

*Significance: The `Hourly Rate (€)` is used when you assign an employee to a timed task in "Manage Products," contributing to "Direct Labor Costs".*

---
### Manage Standard Production Tasks & Manage Standard Shipping Tasks
*Purpose: To define reusable lists of common tasks for production and shipping.*

*Concept: Standardizing task names (e.g., "Weighing Ingredients," "Box Assembly") creates a consistent vocabulary for your operations, simplifying the process of assigning labor activities to products.*

**How to Use:**
- Add, edit, or delete task names in the respective sections.
- Click the corresponding "Save" button.

**Key Fields & Concepts:**
- `Task Name*`: A clear, descriptive name for the activity. *Required.*

*Significance: These tasks become the building blocks for calculating labor costs when you assign them to products in the "Manage Products" section.*

---
### 🌍 Global Costs/Salaries
*Purpose: To define business-wide fixed costs (overheads) and fixed monthly salaries for employees whose work supports the entire business.*

*Concept: **Overheads** are essential business expenses not directly traceable to a single product unit (e.g., rent, utilities, admin salaries). To get a true profitability picture, a portion of these costs must be allocated to each product.*

**Monthly Fixed Overheads:**
- `Global Monthly Rent (€)` & `Global Monthly Utilities (€)`: Enter your total monthly expenses for these items.
- Click **"Save Global Overheads"**.

**Global Monthly Salaries:**
- *Purpose:* For employees on a fixed monthly salary (e.g., admin, marketing, management).
- **How to Use:** Select an employee and enter their `Monthly Salary (€)*`. An employee can only have one global salary entry.
- Click **"Save Global Salaries"**.

*Significance: These global costs are allocated to individual products in the "Manage Products -> Other Costs & Pricing" section, contributing to a more accurate total production cost.*