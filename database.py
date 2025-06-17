import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker

Base = declarative_base()

class Shoe(Base):
    __tablename__ = "shoes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    size_available = Column(String)
    color = Column(String)
    price = Column(Float)
    brand = Column(String)
    image_url = Column(String)
    category = Column(String)
    description = Column(Text)
    quantity_available = Column(Integer)

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, unique=True, index=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    orders = relationship("Order", back_populates="customer")
    cart = relationship("Cart", back_populates="customer", uselist=False)

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    total_amount = Column(Float)
    delivery_address = Column(Text, nullable=True)
    payment_method = Column(String, nullable=True)
    status = Column(String, default="pending")

    customer = relationship("Customer", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")

class Cart(Base):
    __tablename__ = "cart"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), unique=True) # Assuming one cart per customer
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    customer = relationship("Customer", back_populates="cart")
    items = relationship("CartItem", back_populates="cart")


class CartItem(Base):
    __tablename__ = "cart_items"

    id = Column(Integer, primary_key=True, index=True)
    cart_id = Column(Integer, ForeignKey("cart.id"))
    shoe_id = Column(Integer, ForeignKey("shoes.id"))
    quantity = Column(Integer)
    added_at = Column(DateTime, default=datetime.datetime.utcnow)

    cart = relationship("Cart", back_populates="items")
    shoe = relationship("Shoe")


class OrderItem(Base): # Helper table for Order-Shoe many-to-many relationship
    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    shoe_id = Column(Integer, ForeignKey("shoes.id"))
    quantity = Column(Integer)
    price_at_purchase = Column(Float) # Store price at time of order

    order = relationship("Order", back_populates="items")
    shoe = relationship("Shoe")


DATABASE_URL = "sqlite:///./whatsapp_assistant.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def populate_initial_data():
    db = SessionLocal()

    shoes_data = [
        Shoe(name="Nike Air Max", size_available="42", color="Noir", price=55000, brand="Nike", image_url="http://example.com/nike_air_max.jpg", category="Baskets", description="Comfortable running shoes", quantity_available=10),
        Shoe(name="Adidas Stan Smith", size_available="40", color="Blanc", price=45000, brand="Adidas", image_url="http://example.com/adidas_stan_smith.jpg", category="Sneakers", description="Classic leather sneakers", quantity_available=5),
        Shoe(name="Puma Suede", size_available="43", color="Rouge", price=50000, brand="Puma", image_url="http://example.com/puma_suede.jpg", category="Baskets", description="Iconic suede sneakers", quantity_available=8),
        Shoe(name="New Balance 574", size_available="41", color="Gris", price=52000, brand="New Balance", image_url="http://example.com/nb_574.jpg", category="Running", description="Versatile running shoes", quantity_available=12),
        Shoe(name="Converse Chuck Taylor", size_available="39", color="Noir", price=35000, brand="Converse", image_url="http://example.com/converse_chuck.jpg", category="Classiques", description="Timeless canvas shoes", quantity_available=15),
    ]

    try:
        for shoe in shoes_data:
            db.add(shoe)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error populating data: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    create_db_and_tables()
    populate_initial_data()
    print("Database created and initial data populated.")
