from pathlib import Path


structure = [
   "src/shoppingagent/knowledge_base/export_products_jsonl.py", "src/shoppingagent/knowledge_base/seed_mysql.py",
   "src/shoppingagent/knowledge_base/data/productproducts.jsonl"

]

ROOT = Path(__file__).resolve().parent

for i in structure:
   file_path = ROOT / Path(i)
   file_path.parent.mkdir(parents=True, exist_ok=True) 
   file_path.touch(exist_ok=True)
