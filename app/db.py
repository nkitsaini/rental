from fastapi import staticfiles
from tinydb import TinyDB, Query
from typing import Optional

from tinydb.table import Document
import tinydb.table
from .models import *
import base64
from typing import List
import uuid
import enum


class Table(enum.Enum):
	users = enum.auto()
	sessions = enum.auto()
	orders = enum.auto()
	shops = enum.auto()
	items = enum.auto()
	addresses = enum.auto()


class UserAlreadyExists(Exception):
	...


class Database:
	def __init__(self, db_path: str = "tinydb.json") -> None:
		self.database = TinyDB(db_path)
		self.database.table("users")

	def get_table(self, table: Table) -> tinydb.table.Table:
		return self.database.table(table.name)

	def new_user(self, first_name: str, last_name: str, email: str, password: str):
		table = self.get_table(Table.users)
		result = table.search(Query().fragment({"email": email}))
		if len(result) != 0:
			raise UserAlreadyExists()
		table.insert({"first_name": first_name, "last_name": last_name, "email": email, "password": password, "address_ids": []})

	def new_shop(self, name: str, address_id: int) -> int:
		table = self.get_table(Table.shops)
		return table.insert({"name": name, "address_id": address_id, "items": []})

	def add_item_to_shop(self, shop_id: int, item_id: int):
		table = self.get_table(Table.shops)
		shop = table.get(doc_id=shop_id)
		table.update({"items": shop["items"] + [item_id]}, doc_ids=[shop_id])

	def new_item(self, name: str, price: float, image_name: str) -> int:
		table = self.get_table(Table.items)
		return table.insert({"name": name, "price": price, "image_name": image_name})

	def insert_item(self, name: str, price: float) -> int:
		table = self.get_table(Table.items)
		return table.insert({"name": name, "price": price})

	def get_user(self, email: str, password: str) -> Optional[User]:
		table = self.get_table(Table.users)
		UserQuery = Query()
		user = table.get(UserQuery.email == email)
		if user is None:
			return None
		addresses = [self.get_address(a) for a in user['address_ids']]
		user = User.from_doc(user, addresses)
		if user.password == password: return user

	def get_user_orders(self, user_id: int) -> List[Order]:
		table = self.get_table(Table.orders)
		OrderQuery = Query()
		orders = table.search(OrderQuery.user_id == user_id)
		address = [self.get_address(o['address_id']) if o['address_id'] is not None else None for o in orders]
		return [Order.from_doc(o, a) for o, a in zip(orders, address)]

	def get_price(self, order: Order) -> float:
		item = self.get_item(order.item_id)
		return item.price * order.quantity

	def get_order(self, user_id: int, item_id: int, shop_id: int, status: OrderStatus) -> Optional[Order]:
		table = self.get_table(Table.orders)
		OrderQuery = Query()
		order = table.get((OrderQuery.user_id == user_id) & (OrderQuery.item_id == item_id) & (OrderQuery.shop_id == shop_id)
							& (OrderQuery.status == status.name))
		if order is None:
			return None
		address = self.get_address(order['address_id']) if order['address_id'] is not None else None
		return Order.from_doc(order, address)

	def new_order(self, user_id: int, item_id: int, shop_id: int) -> int:
		table = self.get_table(Table.orders)
		now = arrow.now("UTC")
		now_str = now.isoformat()

		order = self.get_order(user_id, item_id, shop_id, OrderStatus.Cart)
		if order is None:
			table.insert({
				"placed_at": now_str,
				"updated_at": now_str,
				"address_id": None,
				"user_id": user_id,
				"item_id": item_id,
				"shop_id": shop_id,
				"quantity": 1,
				"status": OrderStatus.Cart.name
			})
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

	def place_orders(self, user_id: int, address_id: int):
		table = self.get_table(Table.orders)
		now = arrow.now("UTC")
		now_str = now.isoformat()

		OrderQuery = Query()
		table.update({
			"address_id": address_id,
			"status": OrderStatus.Placed.name,
			"updated_at": now_str
		}, (OrderQuery.status == OrderStatus.Cart.name) & (OrderQuery.user_id == user_id))

	def get_shops(self, pincode: int) -> List[Shop]:
		table = self.get_table(Table.shops)
		ShopQuery = Query()
		shops = table.all()
		address_id_to_shop = {shop['address_id']: shop for shop in shops}
		rv = []
		for add_id, shop in address_id_to_shop.items():
			address = self.get_address(add_id)
			if address.pincode == pincode:
				rv.append(Shop.from_doc(shop, address))
		return sorted(rv, key=lambda s: -s.id)

	def get_shop(self, shop_id: int) -> Optional[Shop]:
		table = self.get_table(Table.shops)
		shop = table.get(doc_id=shop_id)
		if shop is None:
			return None
		address = self.get_address(shop['address_id'])
		return Shop.from_doc(shop, address=address)

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
		return self.get_user(user['email'], user['password'])

	def logout_session(self, token: str):
		session = self.get_session(token)
		table = self.get_table(Table.sessions)
		table.remove(doc_ids=[session.id])

	def get_addreses(self, user_id: int) -> List[Address]:
		table = self.get_table(Table.addresses)
		AddressQuery = Query()
		addresses = table.search(AddressQuery.user_id == user_id)
		return [Address.from_doc(a) for a in addresses]
	
	def add_address_to_user(self, address_id: int, user_id: int):
		table = self.get_table(Table.users)
		user = table.get(doc_id=user_id)
		assert user is not None
		table.update({"address_ids": user["address_ids"] + [address_id]}, doc_ids=[user_id])


	def add_address(self, person_name: str, pincode: int, building: str, city: str,
		district: str, state: str, landmark: Optional[str]=None, street: Optional[str]=None,) -> int:
		table = self.get_table(Table.addresses)
		return table.insert({
			"person_name": person_name,
			"pincode": pincode,
			"building": building,
			"city": city,
			"district": district,
			"state": state,
			"landmark": landmark,
			"street": street,
		})

	def get_address(self, address_id: int) -> 'Address':
		table = self.get_table(Table.addresses)
		address = table.get(doc_id=address_id)
		if address is None:
			raise Exception
		return Address.from_doc(address)


	@classmethod
	def doc_to_session(cls, doc: Document) -> Session:
		return Session(doc.doc_id, doc['user_id'], arrow.get(doc['created_at']), doc['token'])

	@classmethod
	def doc_to_item(cls, doc: Document) -> Item:
		return Item(doc.doc_id, doc['name'], doc['price'], doc['image_name'])


if __name__ == "__main__": # testing
	import os
	from faker import Faker
	import httpx
	from pathlib import Path
	from tqdm import tqdm
	from tqdm.asyncio import tqdm_asyncio
	import asyncio as aio
	res = httpx.get('https://fakestoreapi.com/products')
	items = res.json()
	image_dir = Path("static")
	image_dir.mkdir(exist_ok=True, parents=True)
	fake = Faker("en_IN")
	if os.path.exists("rental.json"):
		os.remove("rental.json")
	db = Database("rental.json")
	item_ids = []
	pincodes = [(332404, "Reengus"), (332001, "Mumbai")] + [(int(fake.postcode()), fake.city()) for i in range(0)]
	shop_ids = []

	async def get_image(item):
		async with httpx.AsyncClient() as conn:
			a = await conn.get(item['image'])
		image_name: str = item['image'].split("/")[-1]
		(image_dir / image_name).write_bytes(a.content)

		item_ids.append(db.new_item(item['title'], item['price'] * 70, image_name))

	async def get_images():
		await tqdm_asyncio.gather([get_image(item) for item in items])


	aio.run(get_images())

	print("items done")
	# add new user like this
	db.new_user("ankit", "saini", "ankit@nkit.dev", "some")
	user = db.get_user("ankit@nkit.dev", "some")
	assert user is not None
	for i in range(2):
		for (code, city) in pincodes:
			address_id = db.add_address(fake.first_name(), code, fake.building_number(), city, "Dist" or fake.district(), fake.state(), street=fake.street_name())
			db.add_address_to_user(address_id, user.id)

	# add new shop like this
	for i in tqdm(range(30)):
		for (code, city) in tqdm(pincodes):
			address_id = db.add_address(fake.first_name(), code, fake.building_number(), city, "Dist" or fake.district(), fake.state(), street=fake.street_name())
			shop_ids.append(db.new_shop(fake.first_name() + " Store", address_id))

	for it_id in tqdm(item_ids):
		for sh_id in tqdm(shop_ids):
			db.add_item_to_shop(sh_id, it_id)
