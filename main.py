import json
import csv
import re
from bs4 import BeautifulSoup

# Input and output paths
INPUT_JSON = r"C:\Users\Abhishek Sunilkumar\Downloads\Sticker priya 03-01-2025 - Sheet14.json"
OUTPUT_CSV = "output.csv"

# Columns in the final CSV (order matters):
# The first 8 columns are product-level; columns 9 and 10 are the repeated nutrient rows.
CSV_COLUMNS = [
    "SKU",
    "Title",
    "Description",
    "Allergen",
    "Ingredients",
    "Storage",
    "Weight",
    "Origin",
    "Nutrient",
    "Quantity",
]

##############################################################################
# STEP 1: Read JSON and group by SKU, capturing the Czech translation data.
##############################################################################

# Dictionary to store {sku: {"title": ..., "body_html": ...}}
products = {}

with open(INPUT_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)
    for record in data:
        sku = record.get("sku", "")
        if not sku:
            continue
        if sku not in products:
            products[sku] = {}

        key = record.get("key")  # e.g. "title" or "body_html"
        # We only care about the 'translation' field (the Czech version)
        translation = record.get("translation", "")

        if key == "title":
            products[sku]["title"] = translation
        elif key == "body_html":
            products[sku]["body_html"] = translation

##############################################################################
# STEP 2: Parse each product's Czech HTML to extract fields + split nutrients.
##############################################################################

# Regex to find each “Something(...)” in the nutrient string
NUTRIENT_ITEM_REGEX = re.compile(r'([^,]+\([^)]*\))')
# Regex to separate the name vs. quantity inside parentheses
NUTRIENT_NAME_AND_QTY_REGEX = re.compile(r'(.*?)\((.*?)\)')


def parse_nutrients(nutrient_text):
    """
    Given a raw nutrient string like:
      "Celkové Tuky(99.7g),Sacharidy(0g), Cukr(0g), Vitamin A(700), Bílkoviny(0g)"
    Return a list of (name, quantity) pairs, e.g.:
      [
        ("Celkové Tuky", "99.7g"),
        ("Sacharidy", "0g"),
        ("Cukr", "0g"),
        ("Vitamin A", "700"),
        ("Bílkoviny", "0g")
      ]
    """
    items = NUTRIENT_ITEM_REGEX.findall(nutrient_text or "")
    results = []
    for item in items:
        item = item.strip()
        m = NUTRIENT_NAME_AND_QTY_REGEX.match(item)
        if m:
            name = m.group(1).strip()
            qty = m.group(2).strip()
            results.append((name, qty))
        else:
            # If no match, treat entire item as name
            results.append((item, ""))
    return results


def extract_field(soup, labels):
    """
    Search <p> tags for a <strong> whose text matches any label in 'labels'
    (case-insensitive). If found, remove <strong> and return the rest of that <p>.
    """
    for p in soup.find_all("p"):
        strong = p.find("strong")
        if strong:
            strong_text = strong.get_text(strip=True).lower()
            for label in labels:
                if label.lower() in strong_text:
                    # remove <strong> and return the leftover text
                    strong.extract()
                    return p.get_text(strip=True)
    return ""


def extract_description(soup):
    """
    Returns the text of the first <p> that is NOT one of our known labeled fields.
    In practice, this usually is the main descriptive paragraph.
    """
    known_markers = ["živiny", "složení", "ingredience", "skladování", "hmotnost", "původ", "allergen"]
    for p in soup.find_all("p"):
        strong = p.find("strong")
        if strong:
            st_text = strong.get_text(strip=True).lower()
            # If this paragraph has a known marker, skip it
            if any(marker in st_text for marker in known_markers):
                continue
        # Otherwise, treat this <p> as the product description
        return p.get_text(strip=True)
    return ""


##############################################################################
# STEP 3: Build final rows.  For each product:
#         1) Extract product-level fields
#         2) Split nutrients
#         3) For the first nutrient row, fill product columns
#         4) For subsequent nutrient rows, leave product columns blank
##############################################################################

def build_rows_for_product(sku, title, body_html):
    """
    Parse the HTML for description, allergen, ingredients, storage, weight, origin, and nutrients.
    Then create multiple CSV rows: the first row has product fields + first nutrient,
    subsequent rows only have the next nutrients in the 'Nutrient' and 'Quantity' columns.
    """
    soup = BeautifulSoup(body_html or "", "html.parser")

    description = extract_description(soup)
    allergen = extract_field(BeautifulSoup(body_html, "html.parser"), ["Allergen"])
    # ingredients may appear as "Složení" or "Ingredience"
    ingredients = extract_field(BeautifulSoup(body_html, "html.parser"), ["Složení", "Ingredience"])
    storage = extract_field(BeautifulSoup(body_html, "html.parser"), ["Skladování"])
    weight = extract_field(BeautifulSoup(body_html, "html.parser"), ["Hmotnost"])
    origin = extract_field(BeautifulSoup(body_html, "html.parser"), ["Původ"])

    # Nutrient block:
    nutrient_block = extract_field(BeautifulSoup(body_html, "html.parser"), ["Živiny"])
    nutrient_pairs = parse_nutrients(nutrient_block)

    # If no nutrients, we produce exactly one row with blank nutrient columns
    if not nutrient_pairs:
        return [{
            "SKU": sku,
            "Title": title,
            "Description": description,
            "Allergen": allergen,
            "Ingredients": ingredients,
            "Storage": storage,
            "Weight": weight,
            "Origin": origin,
            "Nutrient": "",
            "Quantity": ""
        }]

    # Otherwise, multiple rows.  The first row has product info + the first nutrient
    rows = []
    for i, (nut_name, nut_qty) in enumerate(nutrient_pairs):
        if i == 0:
            rows.append({
                "SKU": sku,
                "Title": title,
                "Description": description,
                "Allergen": allergen,
                "Ingredients": ingredients,
                "Storage": storage,
                "Weight": weight,
                "Origin": origin,
                "Nutrient": nut_name,
                "Quantity": nut_qty
            })
        else:
            # subsequent nutrient row => blank product fields
            rows.append({
                "SKU": "",
                "Title": "",
                "Description": "",
                "Allergen": "",
                "Ingredients": "",
                "Storage": "",
                "Weight": "",
                "Origin": "",
                "Nutrient": nut_name,
                "Quantity": nut_qty
            })
    return rows


##############################################################################
# STEP 4: Generate final CSV rows for each SKU and write to output.
##############################################################################

all_csv_rows = []
for sku, info in products.items():
    title = info.get("title", "")
    body_html = info.get("body_html", "")
    product_rows = build_rows_for_product(sku, title, body_html)
    all_csv_rows.extend(product_rows)

# Write CSV
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for row in all_csv_rows:
        writer.writerow(row)

print(f"Data successfully written to {OUTPUT_CSV}")