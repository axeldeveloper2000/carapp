from flask import Flask, request, render_template_string, send_file
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import io

app = Flask(__name__)

HTML_TEMPLATE = """
<!doctype html>
<title>Car Price Comparator</title>
<h2>Compare Car Prices: WebAutoBid vs SS.com</h2>
<form method=post>
  Make (e.g. BMW): <input type=text name=make><br>
  Pages to scrape from SS.com (default 2): <input type=number name=pages value=2><br><br>
  <input type=submit value=Compare>
</form>
{% if table %}
  <h3>Comparison Result:</h3>
  {{ table | safe }}
  <br><br>
  <a href="/download">Download CSV</a>
{% endif %}
"""

last_df = pd.DataFrame()  # Ensure this is initialized globally

def extract_make_model(title):
    parts = title.strip().split()
    make = parts[0] if parts else "Unknown"
    model = ' '.join(parts[1:3]) if len(parts) > 2 else parts[1] if len(parts) > 1 else "Unknown"
    return make, model

def scrape_webautobid(make_filter):
    url = 'https://www.webautobid.eu/lv/auctions'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    results = []
    for car in soup.select('.carbox'):
        title_el = car.select_one('.title')
        bid_el = car.select_one('.bid')
        if not title_el or not bid_el:
            continue
        title = title_el.get_text(strip=True)
        if make_filter.lower() in title.lower():
            year_match = re.search(r'\b(19|20)\d{2}\b', title)
            price = bid_el.get_text(strip=True).replace('€','').replace(',','').strip()
            if year_match and price.replace('.', '', 1).isdigit():
                make, model = extract_make_model(title)
                results.append({
                    'make': make,
                    'model': model,
                    'year': int(year_match.group()),
                    'price': int(float(price)),
                    'source': 'WebAutoBid'
                })
    return results

def scrape_ss(make_filter, pages=2):
    results = []
    for page in range(1, pages + 1):
        url = f"https://www.ss.com/lv/transport/cars/{make_filter.lower()}/sell/page{page}.html"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.select('tr[align="center"]')
        for row in rows:
            cells = row.select('td')
            if len(cells) >= 6:
                title = cells[2].get_text(strip=True)
                year_match = re.search(r'\b(19|20)\d{2}\b', title)
                price = cells[4].get_text(strip=True).replace('€','').replace(' ','').replace(',','')
                if year_match and price.isdigit():
                    make, model = extract_make_model(title)
                    results.append({
                        'make': make,
                        'model': model,
                        'year': int(year_match.group()),
                        'price': int(price),
                        'source': 'SS.com'
                    })
    return results

def compare_prices(data):
    df = pd.DataFrame(data)
    if df.empty:
        return pd.DataFrame(columns=['make', 'model', 'year', 'SS.com', 'WebAutoBid', 'difference (€)'])
    grouped = df.groupby(['source', 'make', 'model', 'year'])['price'].median().reset_index()
    comparison = grouped.pivot_table(index=['make', 'model', 'year'], columns='source', values='price').reset_index()
    comparison['difference (€)'] = comparison.get('SS.com', 0) - comparison.get('WebAutoBid', 0)
    return comparison

@app.route('/', methods=['GET', 'POST'])
def index():
    global last_df
    table_html = None
    if request.method == 'POST':
        make = request.form.get('make', 'BMW')
        pages = int(request.form.get('pages', 2))
        web_data = scrape_webautobid(make)
        ss_data = scrape_ss(make, pages)
        all_data = web_data + ss_data
        last_df = compare_prices(all_data)
        table_html = last_df.to_html(index=False)
    return render_template_string(HTML_TEMPLATE, table=table_html)

@app.route('/download')
def download():
    global last_df
    buffer = io.StringIO()
    last_df.to_csv(buffer, index=False)
    buffer.seek(0)
    return send_file(io.BytesIO(buffer.getvalue().encode()),
                     mimetype='text/csv',
                     as_attachment=True,
                     download_name='car_price_comparison.csv')

if __name__ == '__main__':
    app.run(debug=True)