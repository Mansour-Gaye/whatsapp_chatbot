from fastapi import FastAPI

app = FastAPI(title="WhatsApp Business API Assistant", version="0.1.0")

@app.on_event("startup")
async def startup_event():
    # This is a good place to ensure database tables are created.
    print("Application startup: Ensuring database and tables are created.")
    from database import create_db_and_tables
    create_db_and_tables() # This should be idempotent

@app.get("/")
async def root():
    return {"message": "Welcome to the WhatsApp Business API Assistant!"}

from routers import shoes as shoes_router
from routers import cart as cart_router
from routers import orders as orders_router
from routers import whatsapp as whatsapp_router

app.include_router(shoes_router.router, prefix="/api/v1", tags=["Shoes"])
app.include_router(cart_router.router, prefix="/api/v1", tags=["Cart"])
app.include_router(orders_router.router, prefix="/api/v1", tags=["Orders"])
app.include_router(whatsapp_router.router, prefix="", tags=["WhatsApp Webhook"]) # No /api/v1 prefix for webhook

if __name__ == "__main__":
    import uvicorn
    # Note: For production, you'd run Uvicorn directly, not like this.
    print("Running Uvicorn development server...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # Use string "main:app" for reload
