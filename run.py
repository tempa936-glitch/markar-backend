# """
# run.py — Windows-safe startup
# Multiprocessing ke liye freeze_support() zaroori hai Windows pe.
# Usage: python run.py
# """
# import multiprocessing
# import uvicorn

# if __name__ == "__main__":
#     # Windows pe subprocess spawn ke liye ye line ZAROORI hai
#     multiprocessing.freeze_support()

#     uvicorn.run(
#         "app.main:app",
#         host="0.0.0.0",
#         port=8000,
#         reload=False,   # reload=True multiprocessing se conflict karta hai
#         workers=1,
#     )
