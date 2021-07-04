from dataclasses import dataclass
import base64
import enum
from typing import Set
from typing import List, Dict, Optional
import arrow
from tinydb.table import Document


@dataclass
class Address: # will be used for both user address and shop address
	id: int
	person_name: str
	pincode: int
	building: str
	street: Optional[str]
	landmark: Optional[str]
	city: str
	district: str
	state: str

	@classmethod
	def from_doc(cls, doc: Document) -> 'Address':
		return cls(
			doc.doc_id,
			doc['person_name'],
			doc['pincode'],
			doc['building'],
			doc['street'],
			doc['landmark'],
			doc['city'],
			doc['district'],
			doc['state'],
		)
	
	def repr_short(self) -> str:
		return f"{self.building}, {self.city}"


@dataclass
class User:
	id: int
	email: str
	password: str
	first_name: str
	last_name: str
	addresses: List[Address]

	@classmethod
	def from_doc(cls, doc: Document, addresses: List[Address]) -> 'User':
		return cls(
			id=doc.doc_id,
			email=doc['email'],
			password=doc['password'],
			first_name=doc['first_name'],
			last_name=doc['last_name'],
			addresses=addresses,
		)


class OrderStatus(enum.Enum):
	Cart = enum.auto()
	Placed = enum.auto()
	Delivered = enum.auto()


@dataclass
class Order:
	id: int
	placed_at: arrow.Arrow
	updated_at: arrow.Arrow
	user_id: int
	item_id: int
	shop_id: int
	quantity: int
	status: OrderStatus
	address: Optional[Address]

	@classmethod
	def from_doc(cls, doc: Document, address: Optional[Address]) -> 'Order':
		return cls(
			doc.doc_id, arrow.get(doc['placed_at']), arrow.get(doc['updated_at']), doc['user_id'], doc['item_id'],
			doc['shop_id'], doc['quantity'], OrderStatus[doc['status']], address
		)


@dataclass
class Shop:
	id: int
	name: str
	address: Address
	items: Set[int]

	@classmethod
	def from_doc(cls, doc: Document, address: Address) -> 'Shop':
		return cls(doc.doc_id, doc['name'], address, doc['items'])


@dataclass
class Item:
	id: int
	name: str
	price: float
	image_name: str

	@classmethod
	def from_doc(cls, doc: Document) -> "Item":
		return cls(doc.doc_id, doc['name'], doc['price'], doc['image_name'])


@dataclass
class Session:
	id: int
	user_id: int
	created_at: arrow.Arrow
	token: str


if __name__ == "__main__":
	print(OrderStatus["Cart"])