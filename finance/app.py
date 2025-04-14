import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

db.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        symbol TEXT NOT NULL,
        shares INTEGER NOT NULL,
        price NUMERIC NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
""")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # select user's stock portfolio and cash total
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]
    assets = db.execute("""
                SELECT symbol, SUM(shares) as total_shares
                FROM history
                WHERE user_id = ?
                GROUP BY symbol
                HAVING total_shares > 0
            """, session["user_id"])

    total_value = cash

    for asset in assets:
        look = lookup(asset["symbol"])
        asset["name"] = look["name"]
        asset["price"] = look["price"]
        asset["total"] = asset["price"] * asset["total_shares"]
        total_value += asset["total"]

    return render_template("index.html", cash=cash, assets=assets, total_value=total_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # if GET method, display buy form
    if request.method == "GET":
        return render_template("buy.html")

    # if POST method
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        quote = lookup(symbol)

        # if symbol invalid or null
        if quote == None:
            return apology("must provide valid stock symbol", 400)

        if not shares:
            return apology("must provide number of shares", 400)

        try:
            shares = int(shares)
            if shares <= 0:
                return apology("must be a positive whole number", 400)

        except ValueError:
            return apology("shares must be a whole number", 400)

        symbol = symbol.upper()
        cost = quote["price"] * shares

        # ensure user has sufficent balance to purchase, return error if insufficent
        balance = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        balance = balance[0]['cash']

        if cost > balance:
            return apology("insufficient funds", 400)

        # update cash in user balance
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?",
                   cost, session["user_id"])

        # update history table
        db.execute("INSERT INTO history (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   session["user_id"], symbol, shares, quote['price'])

    # redirect back to index page
    flash("Bought!")
    return redirect("/")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute(
        "SELECT symbol, shares, price, timestamp FROM history WHERE user_id = ?", session["user_id"])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/login")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # if GET method, return quote.html
    if request.method == "GET":
        return render_template("quote.html")

    # if POST method, get stock info, makign sure it's valid
    else:
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)
        symbol = lookup(request.form.get("symbol"))

        # if stock symbol does not exist
        if symbol == None:
            return apology("invalid stock symbol", 400)

        return render_template("quoted.html", symbol=symbol)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)

        # ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords do not match", 400)

        # Save username and password as variables
        username = request.form.get("username")
        password = request.form.get("password")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        if len(rows) == 1:
            return apology("username already exist", 400)
        else:
            hash = generate_password_hash(password)
            db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", username, hash)

        # redirect to login page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # if GET method, display sell form
    if request.method == "GET":
        symbols = db.execute("""
                            SELECT symbol
                            FROM history
                            WHERE user_id = ?
                            GROUP BY symbol
                            HAVING SUM(shares) > 0
                            """, session["user_id"])

        return render_template("sell.html", assets=symbols)

    # if POST method
    else:
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        quote = lookup(symbol)
        rows = db.execute("""
                          SELECT symbol, SUM(shares) as total_shares
                          FROM history
                          WHERE user_id = ? AND symbol = ?
                          GROUP BY symbol
                          """, session["user_id"], symbol)

        # return pology is symbol invalid
        if quote == None:
            return apology("must provide valid stock symbol", 400)

        # return apology is shares not provided
        if not shares:
            return apology("must provide number of shares", 400)

        oldshares = rows[0]["total_shares"]
        shares = int(shares)

        # return apology if stock not owned or insufficient shares
        if not rows or oldshares < shares:
            return apology("insufficient shares to sell", 400)

        # sale value
        sold = quote["price"] * shares

        # update cash balance
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", sold, session["user_id"])
        db.execute("INSERT INTO history (user_id, symbol, shares, price) VALUES (?, ?, ?, ?)",
                   session["user_id"], symbol, -shares, quote["price"])

        flash("Sold!")
        return redirect("/")


@app.route("/password", methods=["GET", "POST"])
@login_required
def password():
    """Change user's password"""

    # if GET method, display password change form
    if request.method == "GET":
        return render_template("password.html")

    # if POST method
    else:
        old = request.form.get("old_password")
        new = request.form.get("new_password")
        confirmation = request.form.get("confirmation")

        # ensure all fields are filled
        if not old or not new or not confirmation:
            return apology("must fill out all fields", 400)

        # ensure new password matches
        if new != confirmation:
            return apology("new passwords do not match", 400)

        # query current user data
        user = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

        if not user or not check_password_hash(user[0]["hash"], old):
            return apology("invalid current password", 403)

        # hash new password
        new_hash = generate_password_hash(new)

        # update new hash in db
        db.execute("UPDATE users SET hash = ? WHERE id = ?", new_hash, session["user_id"])

        # logout the user by clearing session
        session.clear()

        # redirect to login
        return redirect("/login")
