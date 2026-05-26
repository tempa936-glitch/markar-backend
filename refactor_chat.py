import os

file_path = r"d:\Makar.ai\Backend\MarkarServer\app\routes\chat.py"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("await get_router().route(req.message, req.model)", "await get_router().route(req.message, req.model, user.user_id)")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated chat.py route calls.")
