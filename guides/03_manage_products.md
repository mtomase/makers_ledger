*Purpose: This is the central hub for defining each of your sellable products and all their associated cost components. The data entered here directly drives the calculations in the "Product Cost Breakdown" analysis.*

*Concept: Each product you sell has its own unique "recipe" of materials, requires specific labor activities for its creation and shipping, uses particular packaging, and should bear a fair share of your business's overheads. Furthermore, each product might have different selling prices and incur different fees depending on the channel through which it's sold (e.g., retail website vs. a wholesale marketplace). This section allows you to meticulously detail all these aspects for each product.*

### Adding/Editing Basic Product Attributes (Top Table)
*Purpose: This table provides an overview of all your products and allows you to manage their high-level attributes.*

**How to Use:**
- Add new products, edit existing ones, or delete them using the data editor functionalities.
- Click **"Save Product Attribute Changes"** to save.

**Key Fields & Concepts:**
- `Product Name*`: The unique, customer-facing name of your product. *Required.*
- `Batch Size (items)*`: The typical number of finished items you produce in one single manufacturing run. *Required.*
- `Monthly Prod (items)*`: Your estimated total monthly production/sales volume for THIS product. This is used as a denominator when allocating global overheads to this product line. *Required.*

*Tip: When you add a new product and save, it's often automatically selected in the dropdown below for immediate detailed editing.*

---
### Managing Detailed Product Components (Lower Section)
- Once you have products listed, **select a product from the `Select Product to Manage Details:` dropdown**. 
- The expanders below this dropdown will then apply **only to the currently selected product**. You must save changes within each expander for that specific product.

---
#### 🧪 Product Materials (for the selected product)
*Purpose: Define the precise recipe or bill of materials for **one single unit** of the selected product.*

**How to Use:**
- For each ingredient in one unit of the product, select it from the dropdown and enter the `Quantity (grams)*`.
- Click **"Save Materials for [Product Name]"**.

*Significance: Directly determines the "Total Material Cost/Item" in the Cost Breakdown.*

---
#### 🛠️ Product Production Tasks (for the selected product)
*Purpose: Assign specific production labor activities to calculate the direct labor costs for one unit.*

**How to Use:**
- For each production step: select the `Task*`, the `Performed By*` employee, the `Time (min)*`, and the `# Items in Task*`.
- **`# Items in Task` is crucial:** It's the number of items processed in the time specified. If an employee spends 60 mins on a batch of 100 items, enter Time=60, Items=100.
- Click **"Save Production Tasks for [Product Name]"**.

*Significance: Determines the "Total Production Labor Cost/Item".*

---
#### 🚚 Product Shipping Tasks (for the selected product)
*Purpose: Assign direct labor for preparing and shipping items of this product.*

**How to Use:**
- Similar to Production Tasks. Enter the `Task`, `Employee`, `Time (min)`, and `# Items in Task` related to shipping preparation.
- Click **"Save Shipping Tasks for [Product Name]"**.

*Significance: Determines the "Total Shipping Labor Cost/Item (Direct)".*

---
#### 🪙 Other Product Specific Costs & Pricing (for the selected product)
*Purpose: Define all other costs, fees, and pricing parameters specific to this product.*

**Packaging Costs (per Item):**
- `Label Cost/Item (€)` & `Other Pkg Materials Cost/Item (€)`: Direct costs for packaging one item.

**Salary & Overhead Allocation:**
- `Allocate Salary of Employee`: Choose a globally salaried employee to attribute a portion of their salary to this product line.
- `Items of THIS Product per Month (for salary/rent allocation)`: Enter the monthly unit volume of this product that should bear a portion of the selected global salary or the total global rent/utilities.

**Online Selling Fees - Retail/Wholesale Channels:**
- `Avg Order Value (€)`: The typical total value of a customer's order in that channel. Used to distribute per-order fees.
- *Percentage Fees* (e.g., CC Fee, Platform Fee): Entered as decimals (e.g., `0.029` for 2.9%).
- *Flat Fees per Order*: A fixed cost per order, which is then distributed per item.
- `Retail Avg Shipping Paid by You (€)`: Your actual shipping expense for an average retail order.

**Pricing Strategy:**
- `Wholesale Price/Item (€)` & `Retail Price/Item (€)`: Your selling prices.
- `Buffer Percentage`: A safety margin added to your production cost to suggest a target price.

**Distribution Mix:**
- `Wholesale Distribution (%)`: The percentage of this product's sales you expect to be wholesale. Retail is the remainder.

**Always click "Save Other Costs & Pricing for [Product Name]" after changes.**