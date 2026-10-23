"""
Python tools the AI agent can call.

The LLM only DECIDES which tool to call; these functions are what actually run.
Every tool returns a dict: {"success": True, ...} or {"success": False, "error": "..."}
so the agent can always explain failures gracefully instead of crashing.
"""

import os
import requests

REQUEST_TIMEOUT = 10  # seconds

WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    61: "slight rain", 63: "moderate rain", 65: "heavy rain",
    71: "slight snow", 73: "moderate snow", 75: "heavy snow",
    80: "slight rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    95: "thunderstorm", 96: "thunderstorm with slight hail", 99: "thunderstorm with heavy hail",
}

# Used ONLY when STOCK_USE_DEMO=true. Not real market data.
DEMO_PRICES = {"AAPL": 225.50, "MSFT": 415.20, "GOOGL": 175.80,
               "AMZN": 185.10, "TSLA": 250.30, "NVDA": 130.40}


def _error(message: str) -> dict:
    return {"success": False, "error": message}


def _http_get(url: str, params: dict, service: str, headers: dict = None, allow_status=()):
    """GET with uniform error handling. Returns (response, error_dict)."""
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.Timeout:
        return None, _error(f"{service} request timed out. Please try again.")
    except requests.exceptions.ConnectionError:
        return None, _error(f"Could not connect to {service}. Check your internet connection.")
    except requests.exceptions.RequestException as exc:
        return None, _error(f"{service} request failed: {exc}")

    if resp.status_code == 429:
        return None, _error(f"{service} rate limit exceeded. Please try again later.")
    if resp.status_code >= 400 and resp.status_code not in allow_status:
        return None, _error(f"{service} returned HTTP {resp.status_code}.")
    return resp, None


# --------------------------------------------------------------------------- #
# Tool 1: weather (Open-Meteo: free, no API key)
# --------------------------------------------------------------------------- #
def get_weather(city: str) -> dict:
    if not isinstance(city, str) or not city.strip():
        return _error("City name cannot be empty.")
    city = city.strip()

    resp, err = _http_get(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": city, "count": 1, "language": "en", "format": "json"},
        "Geocoding service",
    )
    if err:
        return err
    try:
        results = resp.json().get("results")
    except ValueError:
        return _error("Geocoding service returned an invalid response.")
    if not results:
        return _error(f"City '{city}' was not found.")

    place = results[0]
    resp, err = _http_get(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
        },
        "Weather service",
    )
    if err:
        return err
    try:
        current = resp.json()["current"]
    except (ValueError, KeyError):
        return _error("Weather service returned an invalid response.")

    return {
        "success": True,
        "city": place.get("name", city),
        "country": place.get("country", ""),
        "temperature_c": current.get("temperature_2m"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "condition": WEATHER_CODES.get(current.get("weather_code"), "unknown"),
    }


# --------------------------------------------------------------------------- #
# Tool 2: stock price (Yahoo Finance chart API: free, no API key; optional demo mode)
# --------------------------------------------------------------------------- #
YAHOO_HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
BROWSER_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                 "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"}


def get_stock_price(symbol: str) -> dict:
    if not isinstance(symbol, str) or not symbol.strip():
        return _error("Stock symbol cannot be empty.")
    symbol = symbol.strip().upper()

    if os.getenv("STOCK_USE_DEMO", "false").lower() == "true":
        if symbol in DEMO_PRICES:
            return {"success": True, "symbol": symbol, "price": DEMO_PRICES[symbol],
                    "currency": "USD", "source": "DEMO DATA (not real-time)"}
        return _error(f"No demo price is available for {symbol}.")

    last_error = _error("Stock data service is unavailable.")
    for host in YAHOO_HOSTS:  # second host is a fallback
        resp, err = _http_get(
            f"https://{host}/v8/finance/chart/{symbol}",
            {"interval": "1d", "range": "1d"},
            "Stock data service",
            headers=BROWSER_HEADERS,
            allow_status=(404,),  # Yahoo uses 404 + JSON body for unknown symbols
        )
        if err:
            last_error = err
            continue
        try:
            chart = resp.json()["chart"]
        except (ValueError, KeyError):
            last_error = _error("Stock data service returned an invalid response.")
            continue

        if chart.get("error") or not chart.get("result"):
            return _error(f"No price data found for symbol '{symbol}'.")
        try:
            meta = chart["result"][0]["meta"]
            price = meta["regularMarketPrice"]
        except (KeyError, IndexError, TypeError):
            last_error = _error(f"Could not parse price data for symbol '{symbol}'.")
            continue
        return {
            "success": True,
            "symbol": meta.get("symbol", symbol),
            "name": meta.get("longName") or meta.get("shortName") or symbol,
            "price": round(float(price), 2),
            "currency": meta.get("currency", "USD"),
            "exchange": meta.get("fullExchangeName", ""),
            "source": "Yahoo Finance (may be delayed)",
        }
    return last_error


# --------------------------------------------------------------------------- #
# Tool 3: calculate position value (stock price x quantity)
# --------------------------------------------------------------------------- #
def calculate_stock_value(symbol: str, quantity: float) -> dict:
    try:
        quantity = float(quantity)
    except (TypeError, ValueError):
        return _error("Quantity must be a number.")
    if quantity <= 0:
        return _error("Quantity must be greater than zero.")

    price = get_stock_price(symbol)
    if not price["success"]:
        return price
    return {
        **price,
        "quantity": quantity,
        "total_value": round(price["price"] * quantity, 2),
    }


# --------------------------------------------------------------------------- #
# Registry + safe dispatcher (the Python side that actually executes tools)
# --------------------------------------------------------------------------- #
TOOL_REGISTRY = {
    "get_weather": get_weather,
    "get_stock_price": get_stock_price,
    "calculate_stock_value": calculate_stock_value,
}


def execute_tool(name: str, arguments: dict) -> dict:
    func = TOOL_REGISTRY.get(name)
    if func is None:
        return _error(f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        return _error("Tool arguments must be a JSON object.")
    try:
        return func(**arguments)
    except TypeError as exc:
        return _error(f"Invalid arguments for {name}: {exc}")
    except Exception as exc:  # never let a tool crash the agent
        return _error(f"Tool '{name}' failed: {exc}")