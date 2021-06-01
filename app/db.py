from tinydb import TinyDB, Query
from typing import Optional

from tinydb.table import Document
import tinydb.table
from .models import *
from typing import List
import uuid
import enum


class Table(enum.Enum):
	users = enum.auto()
	sessions = enum.auto()
	orders = enum.auto()
	shops = enum.auto()
	items = enum.auto()

class UserAlreadyExists(Exception):
	...

class Database:
	def __init__(self, db_path: str = "tinydb.json") -> None:
		self.database = TinyDB(db_path)
		self.database.table("users")
	
	def get_table(self, table: Table) -> tinydb.table.Table:
		return self.database.table(table.name)
	
	def new_user(self, first_name: str, last_name: str, email: str, password: str, address: str):
		table = self.get_table(Table.users)
		result = table.search(Query().fragment({"email": email}))
		if len(result) != 0:
			raise UserAlreadyExists()
		table.insert({"first_name": first_name, "last_name": last_name, "email": email, "password": password, "address": address})

	def new_shop(self, name: str, pincode: str, address: str) -> int:
		table = self.get_table(Table.shops)
		return table.insert({"name": name, "pincode": pincode, "address": "mumbai", "items": []})

	def add_item_to_shop(self, shop_id: int, item_id: int):
		table = self.get_table(Table.shops)
		shop = table.get(doc_id=shop_id)
		table.update({"items": shop["items"] + [item_id]}, doc_ids=[shop_id])

	def new_item(self, name: str, price: float) -> int:
		table = self.get_table(Table.items)
		return table.insert({"name": name, "price": price})

	def insert_item(self, name: str, price: float) -> int:
		table = self.get_table(Table.items)
		return table.insert({"name": name, "price": price})
	
	def get_user(self, email: str, password: str) -> Optional[User]: # None ...
		table = self.get_table(Table.users)
		UserQuery = Query()
		user = table.get(UserQuery.email == email)
		if user is None:
			return None
		return self.doc_to_user(user)
	
	def get_user_orders(self, user_id: int) -> List[Order]:
		table = self.get_table(Table.orders)
		OrderQuery = Query()
		orders = table.search(OrderQuery.user_id == user_id)
		return [Order.from_doc(o) for o in orders]
	
	def get_price(self, order: Order) -> float:
		item = self.get_item(order.item_id)
		return item.price * order.quantity
	
	def get_order(self,  user_id: int, item_id: int, shop_id: int, status: OrderStatus) -> Optional[Order]:
		table = self.get_table(Table.orders)
		OrderQuery = Query()
		order = table.get((OrderQuery.user_id == user_id) & (OrderQuery.item_id == item_id) & (OrderQuery.shop_id==shop_id) & (OrderQuery.status==status.name))
		if order is None:
			return None
		return Order.from_doc(order)

	def new_order(self, user_id: int, item_id: int, shop_id: int) -> int:
		table = self.get_table(Table.orders)
		now = arrow.now("UTC")
		now_str = now.isoformat()

		order = self.get_order(user_id, item_id, shop_id, OrderStatus.Cart)
		if order is None:
			table.insert({"placed_at": now_str, "updated_at": now_str, "user_id": user_id, "item_id": item_id, "shop_id": shop_id, "quantity": 1, "status": OrderStatus.Cart.name})
			return 1
		else:
			table.update({"updated_at": now_str, "quantity": order.quantity + 1}, doc_ids=[order.id])
			return order.quantity + 1

	def decrease_order_quantity(self, user_id: int, item_id: int, shop_id: int) -> int:
		table = self.get_table(Table.orders)
		now = arrow.now("UTC")
		now_str = now.isoformat()

		order = self.get_order(user_id, item_id, shop_id, OrderStatus.Cart)
		if order is None:
			return 0
		else:
			if order.quantity == 1:
				table.remove(doc_ids=[order.id])
				return 0
			table.update({"updated_at": now_str, "quantity": order.quantity - 1}, doc_ids=[order.id])
			return order.quantity - 1

	def place_orders(self, user_id: int):
		table = self.get_table(Table.orders)
		now = arrow.now("UTC")
		now_str = now.isoformat()

		OrderQuery = Query()
		table.update({"status": OrderStatus.Placed.name, "updated_at": now_str}, (OrderQuery.status == OrderStatus.Cart.name) & (OrderQuery.user_id == user_id))
	
	def get_shops(self, pincode: str) -> List[Shop]:
		table = self.get_table(Table.shops)
		ShopQuery = Query()
		shops = table.search(ShopQuery.pincode == pincode)
		return [self.doc_to_shop(s) for s in shops]

	def get_shop(self, shop_id: int) -> Optional[Shop]:
		table = self.get_table(Table.shops)
		shop = table.get(doc_id=shop_id)
		if shop is None:
			return None
		return self.doc_to_shop(shop)

	def get_items(self, shop: Shop) -> List[Item]:
		return [self.get_item(i) for i in shop.items]
	
	def get_item(self, item_id: int) -> Item:
		table = self.get_table(Table.items)
		item = table.get(doc_id=item_id)
		if item is None:
			raise Exception
		return self.doc_to_item(item)
	
	def create_session(self, user_id: int) -> Session:
		table = self.get_table(Table.sessions)
		now = arrow.now("UTC")
		now_str = now.isoformat()
		token = uuid.uuid4().hex
		id = table.insert({"created_at": now_str, "user_id": user_id, "token": token})
		return self.doc_to_session(table.get(doc_id=id)) # type: ignore
	
	def get_session(self, token: str) -> Optional[Session]:
		table = self.get_table(Table.sessions)
		query = Query()
		session = table.get(query.token == token)
		if session is None:
			return None
		return self.doc_to_session(session)
	
	def get_logged_in_user(self, token: str) -> Optional[User]:
		session = self.get_session(token)
		if session is None:
			return None
		user_table = self.get_table(Table.users)

		user = user_table.get(doc_id=session.user_id)
		if user is None:
			return None
		return self.doc_to_user(user)
	
	def logout_session(self, token: str):
		session = self.get_session(token)
		table = self.get_table(Table.sessions)
		table.remove(doc_ids=[session.id])
		
		
	@classmethod
	def doc_to_user(cls, doc: Document) -> User:
		return User(doc.doc_id, doc['email'], doc['password'], doc['first_name'], doc['last_name'], doc['address'])

	@classmethod
	def doc_to_session(cls, doc: Document) -> Session:
		return Session(doc.doc_id, doc['user_id'], arrow.get(doc['created_at']), doc['token'])
	
	@classmethod
	def doc_to_shop(cls, doc: Document) -> Shop:
		return Shop(doc.doc_id, doc['name'], doc['pincode'], doc['address'], doc['items'])
	
	@classmethod
	def doc_to_item(cls, doc: Document) -> Item:
		return Item(doc.doc_id, doc['name'], doc['price'])




if __name__ == "__main__": # testing
	import os
	if os.path.exists("/tmp/test.json"):
		os.remove("/tmp/test.json")
	db = Database("/tmp/test.json")
	db.new_user("ankit", "saini", "ankit@nkit.dev", "some", "AK Plaza, Reengus")
	user = db.get_user("a@a.dev", "some")
	shop_id = db.new_shop("general store", "332404", "reengus")

	item_id = db.new_item("brush", 3.2)
	db.add_item_to_shop(shop_id, item_id)
	db.new_order(user.id, item_id, shop_id)
	db.new_order(user.id, item_id, shop_id)
	db.new_order(user.id, item_id, shop_id)

	item_id = db.new_item("soap", 7)
	db.add_item_to_shop(shop_id, item_id)
	db.new_order(user.id, item_id, shop_id)


	print(db.get_shops("332404"))
	# print(db.get_user("ankit@nkit.dev", "ankit"))
