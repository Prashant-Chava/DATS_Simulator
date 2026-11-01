
from fastapi import FastAPI, HTTPException

app = FastAPI()

customers = {
    1: {"name": "Rahul", "age": 22},
    2: {"name": "Amit", "age": 24},
    3: {"name": "Priya", "age": 21}
}

@app.get("/customers/{customer_id}")
def get_customer(customer_id: int):
    if customer_id not in customers:
        raise HTTPException(
            status_code=404,
            detail="Customer not found"
        )

    return customers[customer_id]
