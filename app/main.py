from fastapi import FastAPI, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from . import models, schemas, database, observability
import time
from sqlalchemy.exc import OperationalError
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import logging

app = FastAPI()

# Setup observability
observability.setup_observability(app)

# Dependency
def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.on_event("startup")
async def startup_event():
    max_retries = 5
    retry_delay = 5
    for i in range(max_retries):
        try:
            database.create_tables()
            print("Database tables created successfully")
            break
        except OperationalError:
            if i < max_retries - 1:
                print(f"Database not ready, retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                print("Max retries reached. Could not connect to the database.")
                raise

# Custom handler for 422 errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logging.error(f"Validation error for request {request.url}: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )

@app.post("/items/", response_model=schemas.Item)
def create_item(item: schemas.ItemCreate, db: Session = Depends(get_db)):
    try:
        logging.info("Attempting to create a new item", extra={"item_data": item.dict()})
        db_item = models.Item(**item.dict())
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
        logging.info(f"Successfully created new item: {db_item.id}", extra={"item_name": db_item.name})
        return db_item
    except HTTPException as http_exc:
        logging.error(f"HTTP error while creating item: {str(http_exc)}")
        raise http_exc
    except Exception as e:
        logging.error(f"Failed to create item: {str(e)}", extra={"item_data": item.dict()})
        db.rollback()  # Rollback the transaction in case of an error
        raise HTTPException(status_code=500, detail="Failed to create item")

@app.get("/items/{item_id}", response_model=schemas.Item)
def read_item(item_id: int, db: Session = Depends(get_db)):
    try:
        logging.info(f"Attempting to retrieve item: {item_id}")
        item = db.query(models.Item).filter(models.Item.id == item_id).first()
        if item is None:
            logging.warning(f"Item not found: {item_id}")
            raise HTTPException(status_code=404, detail="Item not found")
        logging.info(f"Successfully retrieved item: {item_id}", extra={"item_name": item.name})
        return item
    except HTTPException as http_exc:
        logging.error(f"HTTP error while retrieving item: {item_id}, error: {str(http_exc)}")
        raise http_exc
    except Exception as e:
        logging.error(f"Unexpected error while retrieving item: {item_id}, error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve item")

# Add more endpoints as needed

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)