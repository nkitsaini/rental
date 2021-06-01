from dataclasses import dataclass
import enum
from typing import Set
from typing import List, Dict
import arrow
from tinydb.table import Document

@dataclass
class User:
	id: int
	email: str
	password: str
	first_name: str
	last_name: str
	address: str

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

	@classmethod
	def from_doc(cls, doc: Document) -> 'Order':
		return cls(
			doc.doc_id,
			arrow.get(doc['placed_at']),
			arrow.get(doc['updated_at']),
			doc['user_id'],
			doc['item_id'],
			doc['shop_id'],
			doc['quantity'],
			OrderStatus[doc['status']]
		)



@dataclass
class Shop:
	id: int
	name: str
	pincode: str
	address: str
	items: Set[int]


@dataclass
class Item:
	id: int
	name: str
	price: float

@dataclass
class Session:
	id: int
	user_id: int
	created_at: arrow.Arrow
	token: str

if __name__ == "__main__":
	print(OrderStatus["Cart"])