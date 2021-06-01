from fastapi import FastAPI, Response, Query
from fastapi.params import Cookie, Depends, Form
from collections import defaultdict
from fastapi import status
import jinja2
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import RedirectResponse
from .models import *
from typing import DefaultDict, Literal, Optional, overload

from .db import Database, UserAlreadyExists

templates = Jinja2Templates("templates")
app = FastAPI()
DEBUG = True

if DEBUG:
	db = Database("/tmp/test.json")
else:
	db = Database("rental.json")

DEFAULT_PIN_CODE = "332404"


@dataclass
class RequiresLoginException(Exception):
	redirect_url: str = "/"


@app.exception_handler(RequiresLoginException)
async def exception_handler(request: Request, exc: RequiresLoginException) -> Response:
	return RedirectResponse(url='/login_page')


@dataclass(frozen=True)
class UserDepends:
	required: bool = False

	def __call__(self, token: Optional[str] = Cookie(None)) -> Optional[User]:
		def not_logged_action():
			if self.required:
				raise RequiresLoginException()
			else:
				return None

		if token is None:
			return not_logged_action()
		user = db.get_logged_in_user(token)
		if user is None:
			return not_logged_action()
		return user


@app.get("/")
def home_page(request: Request, user: Optional[User] = Depends(UserDepends(False))):
	return templates.TemplateResponse("home_page.html", {"request": request, "user": user})


@app.get("/login_page")
def get_login_page(request: Request, user: Optional[User] = Depends(UserDepends(False))):
	if user is not None: # already logged in
		return RedirectResponse("/")
	return templates.TemplateResponse("login_page.html", {"request": request})


@app.get("/sign_up")
def get_singup_page(request: Request, user: Optional[User] = Depends(UserDepends(False))):
	if user is not None: # already logged in
		return RedirectResponse("/")
	return templates.TemplateResponse("signup_page.html", {"request": request})


@app.post("/do_sign_up")
def do_signup(
	request: Request,
	first_name: str = Form(...),
	last_name: str = Form(...),
	email: str = Form(...),
	address: str = Form(...),
	password: str = Form(...),
	confirmation_password: str = Form(...)
):
	if password != confirmation_password:
		return templates.TemplateResponse(
			"signup_page.html", {
				"request": request,
				"error": "Confirmation Password Didn't match"
			}
		)
	try:
		db.new_user(first_name, last_name, email, password, address)
		resp = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
		user = db.get_user(email, password)
		session = db.create_session(user.id)
		resp.set_cookie("token", session.token)
		return resp
	except UserAlreadyExists:
		return templates.TemplateResponse("signup_page.html", {"request": request, "error": "Email is already registered"})


@app.get("/logout")
def logout(request: Request, user: User = Depends(UserDepends(True)), token: str = Cookie(None)):
	db.logout_session(token)
	return RedirectResponse("/")


def is_valid(pin_code: str):
	return len(pin_code) == 6


@app.get("/shops/")
@app.get("/shops/{pin_code}")
def get_shops(request: Request, pin_code: str = DEFAULT_PIN_CODE, page_no: int = Query(0), user: Optional[User] = Depends(UserDepends(False))):
	error = None
	if not is_valid(pin_code):
		error = f"pin_code: {pin_code} not valid"
	shops = db.get_shops(pin_code)

	return templates.TemplateResponse(
		"shop_list.html", {
			"request": request,
			"error": error,
			"shops": shops,
			"invalid_pin_code": error is not None,
			"user": user
		}
	)

@app.get("/see_shops")
def see_shops_form(request: Request, pincode: str):
	return RedirectResponse("/shops/" + pincode)

@app.get("/items/{shop_id}")
def get_items(request: Request, shop_id: int, page_no: int = Query(0), user: Optional[User] = Depends(UserDepends(True))):
	error = None
	shop = db.get_shop(shop_id)
	assert shop is not None

	items = db.get_items(shop)
	item_ids = {i.id for i in items}
	orders = db.get_user_orders(user.id)
	counts = defaultdict(int)
	for o in orders:
		if o.status != OrderStatus.Cart:
			continue
		if o.item_id in item_ids:
			counts[o.item_id] += o.quantity


	return templates.TemplateResponse(
		"item_list.html", {
			"request": request,
			"error": error,
			"items": items,
			"counts": counts,
			"shop": shop,
			"user": user
		}
	)


class OrderInfo(BaseModel):
	shop_id: int
	item_id: int


@app.post("/order/place_order")
async def add_order(request: Request, order_info: OrderInfo, user: User = Depends(UserDepends(True))):
	return db.new_order(user.id, order_info.item_id, order_info.shop_id)


@app.post("/order/decrease_order_quantity")
def remove_order(request: Request, order_info: OrderInfo, user: User = Depends(UserDepends(True))):
	return db.decrease_order_quantity(user.id, order_info.item_id, order_info.shop_id)


@app.post("/order/place_cart_order")
def place_orders(request: Request, user: User = Depends(UserDepends(True))):
	db.place_orders(user.id)


@app.get("/show_orders")
def show_orders_and_cart(request: Request, user: User = Depends(UserDepends(True))):
	orders = db.get_user_orders(user.id)
	shops = {o.shop_id: db.get_shop(o.shop_id) for o in orders}
	items = {o.item_id: db.get_item(o.item_id) for o in orders}
	cart_orders = []
	other_orders = []
	for order in orders:
		if order.status == OrderStatus.Cart:
			cart_orders.append(order)
		else:
			other_orders.append(order)
	total_cart_price = sum(db.get_price(order) for order in cart_orders)
	other_orders.sort(key=lambda x: x.status.value)
	return templates.TemplateResponse(
		"orders.html", {
			"request": request,
			"user": user,
			"cart_orders": cart_orders,
			"other_orders": other_orders,
			"total_cart_price": total_cart_price,
			"shops": shops,
			"items": items
		}
	)


@app.get("/do_login")
def log_user_in_get(request: Request):
	return RedirectResponse(f"/login_page", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/do_login")
def log_user_in(
	request: Request, email: str = Form(...), password: str = Form(...), user: Optional[User] = Depends(UserDepends(False))
):
	if user is not None: # already logged in
		return RedirectResponse("/")
	user = db.get_user(email, password) #
	if user is None:
		return templates.TemplateResponse(
			"login_page.html", {
				"request": request,
				"error": "Please check your email and password again"
			}
		)
	resp = RedirectResponse(f"/", status_code=status.HTTP_303_SEE_OTHER)
	session = db.create_session(user.id)
	resp.set_cookie("token", session.token)
	return resp


@app.get("/debug")
def debug(request: Request, user: Optional[User] = Depends(UserDepends(False))):
	return user.name if user else None


@app.get("/breakpoint")
def debug_bp(request: Request):
	breakpoint()
	return "done"


app.mount("/static", StaticFiles(directory="rental"), "static")

if __name__ == "__main__":
	import uvicorn
	uvicorn.run("app.app:app", reload=True)
