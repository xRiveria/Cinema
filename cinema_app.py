import cloudscraper
import time
from datetime import datetime, timedelta
import json
import urllib.parse
import re
from bs4 import BeautifulSoup

# ==========================================
# PHASE 1: FETCH MASTER LISTS
# ==========================================

def get_gv_movies(scraper):
    print("Fetching Golden Village Master List...")
    timestamp = int(time.time() * 1000)
    url = f"https://www.gv.com.sg/.gv-api/nowshowing?t=101_{timestamp}"
    
    headers = {
        "x_developer": "ENOVAX",
        "origin": "https://www.gv.com.sg",
        "referer": "https://www.gv.com.sg/GVMovies"
    }

    try:
        res = scraper.post(url, headers=headers)
        if res.status_code == 200:
            data = res.json().get('data', [])
            print(f"  -> Found {len(data)} movies at GV.")
            return data
        print(f"  -> GV Failed: {res.status_code}")
        return []
    except Exception as e:
        print(f"  -> GV Error: {e}")
        return []

def get_shaw_movies(scraper):
    # Shaw provides movies + detailed times for one date per request.
    print("Fetching Shaw Theatres Showtimes for the next 7 days...")
    all_movies = []
    base_date = datetime.now()

    for day_offset in range(7):
        target_date = (base_date + timedelta(days=day_offset)).strftime('%Y-%m-%d')
        url = f"https://shaw.sg/internal/get_show_times?date={target_date}&movieId=0&locationId=0&promotionId=0"

        headers = {
            "x-app": "PWSM",
            "x-api-forward-to": "internal",
            "referer": f"https://shaw.sg/showtimes?movie=&location=&date={target_date}",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        }

        try:
            res = scraper.get(url, headers=headers)
            if res.status_code == 200:
                daily_movies = res.json()
                if isinstance(daily_movies, list):
                    for movie in daily_movies:
                        movie["scrapeDate"] = target_date
                        for showtime in movie.get("showTimes", []):
                            showtime.setdefault("displayDate", target_date)
                    all_movies.extend(daily_movies)
                    print(f"  -> {target_date}: pulled {len(daily_movies)} Shaw movies.")
                else:
                    print(f"  -> {target_date}: unexpected Shaw response shape.")
            else:
                print(f"  -> {target_date}: Shaw Failed: {res.status_code}")
        except Exception as e:
            print(f"  -> {target_date}: Shaw Error: {e}")

        time.sleep(0.5) # Polite delay

    print(f"  -> Collected {len(all_movies)} dated Shaw movie entries.")
    return all_movies

def get_eaglewings_movies(scraper):
    print("Fetching EagleWings Master List...")
    try:
        home_url = "https://www.eaglewingscinematics.com.sg/"
        scraper.get(home_url) # Initialize session
        
        xsrf_cookie = scraper.cookies.get('XSRF-TOKEN')
        if not xsrf_cookie:
            print("  -> Failed to retrieve EW token.")
            return []
            
        xsrf_token = urllib.parse.unquote(xsrf_cookie)
        api_url = "https://www.eaglewingscinematics.com.sg/api/v1/film/showings"
        
        headers = {
            "accept": "application/json",
            "x-requested-with": "XMLHttpRequest",
            "x-xsrf-token": xsrf_token,
            "referer": home_url
        }
        
        res = scraper.get(api_url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            print(f"  -> Found {len(data)} movies at EagleWings.")
            return data
            
        print(f"  -> EagleWings Failed: {res.status_code}")
        return []
    except Exception as e:
        print(f"  -> EagleWings Error: {e}")
        return []


# ==========================================
# PHASE 2: FETCH DETAILED SHOWTIMES
# ==========================================

def get_gv_showtimes(scraper, gv_movie_list):
    print("\n--- Pulling Detailed GV Showtimes ---")
    detailed_gv_data = []

    for movie in gv_movie_list:
        film_id = movie.get('filmCd')
        title = movie.get('filmTitle')
        
        safe_title = str(title or "").encode("ascii", "replace").decode("ascii")
        print(f"Checking GV times for: {safe_title[:30]}...")
        timestamp = int(time.time() * 1000)
        showtime_url = f"https://www.gv.com.sg/.gv-api/sessionforfilm?t=115_{timestamp}" 
        
        headers = {
            "x_developer": "ENOVAX",
            "origin": "https://www.gv.com.sg",
            "referer": "https://www.gv.com.sg/GVMovieDetails",
            "content-type": "application/json; charset=UTF-8",
            "accept": "application/json, text/plain, */*"
        }

        payload = {"filmCode": film_id}

        try:
            res = scraper.post(showtime_url, headers=headers, json=payload)
            if res.status_code == 200:
                movie['showTimesData'] = res.json().get('data', res.json())
            else:
                movie['showTimesData'] = {"error": f"Status {res.status_code}"}
        except Exception as e:
            movie['showTimesData'] = {"error": str(e)}
            
        detailed_gv_data.append(movie)
        time.sleep(0.5) # Polite delay

    return detailed_gv_data

# Make sure to include these imports at the top if you don't have them
import re
import json
import time

# --- ADD THESE HELPER FUNCTIONS ABOVE YOUR EAGLEWINGS SHOWTIMES FUNCTION ---

def extract_csrf_token(html: str):
    """Extract Laravel CSRF token from meta tag."""
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    if not match:
        raise Exception("CSRF token not found in meta tags")
    return match.group(1)

def extract_window_vars(html: str):
    """Extract data from window.Vars JS object."""
    vars_match = re.search(r'window\.Vars\s*=\s*{(.*?)};', html, re.DOTALL)
    if not vars_match:
        raise Exception("window.Vars not found in HTML")
    
    vars_block = vars_match.group(1)
    
    scheduledfilm_match = re.search(r'ScheduledFilmId\s*:\s*"([^"]+)"', vars_block)
    cinema_match = re.search(r'CinemaId\s*:\s*"([^"]+)"', vars_block)
    title_match = re.search(r"'Title'\s*:\s*\"([^\"]+)\"", vars_block)
    rating_match = re.search(r"'Rating'\s*:\s*\"([^\"]+)\"", vars_block)

    if not all([scheduledfilm_match, cinema_match, title_match, rating_match]):
        raise Exception("Failed to extract required movie fields from window.Vars")

    return {
        "scheduledfilm_id": scheduledfilm_match.group(1),
        "cinema_id": cinema_match.group(1),
        "title": title_match.group(1),
        "rating": rating_match.group(1),
    }

# --- REPLACE YOUR EXISTING get_eaglewings_showtimes WITH THIS ---

def get_eaglewings_showtimes(scraper, eagle_movie_list):
    print("\n--- Pulling Detailed EagleWings Showtimes ---")
    detailed_ew_data = []
    base_url = "https://www.eaglewingscinematics.com.sg"

    for movie in eagle_movie_list:
        url = movie.get('link')
        original_title = movie.get('title')
        
        if not url:
            continue
            
        safe_title = str(original_title or "").encode("ascii", "replace").decode("ascii")
        print(f"Checking EW times for: {safe_title[:30]}...")
        
        try:
            # 1. Fetch the movie detail page HTML
            page_res = scraper.get(url)
            page_res.raise_for_status()
            html = page_res.text
            
            # 2. Extract specific tokens and variables using your verified logic
            csrf_token = extract_csrf_token(html)
            movie_data = extract_window_vars(html)
            
            # 3. Call the time-scheduled API endpoint
            api_url = f"{base_url}/api/v1/film/time-scheduled"
            
            payload = {
                "movie": {
                    "Title": movie_data["title"],
                    "Rating": movie_data["rating"]
                },
                "cinema_id": movie_data["cinema_id"],
                "scheduledfilm_id": movie_data["scheduledfilm_id"]
            }
            
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "X-CSRF-TOKEN": csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": base_url,
                "Referer": url,
            }
            
            res = scraper.post(api_url, headers=headers, json=payload)
            
            if res.status_code == 200:
                try:
                    movie['showTimesData'] = res.json()
                except json.JSONDecodeError:
                    movie['showTimesData'] = {"error": "Invalid JSON returned"}
            else:
                movie['showTimesData'] = {"error": f"Status {res.status_code}"}
                
        except Exception as e:
            movie['showTimesData'] = {"error": str(e)}
            
        detailed_ew_data.append(movie)
        time.sleep(0.5) # Polite delay

    return detailed_ew_data


def clean_filmhouse_text(value):
    return re.sub(r'\s+', ' ', value or '').strip()


def parse_filmhouse_html(html, date_str):
    soup = BeautifulSoup(html or "", "html.parser")
    movies = []

    for card in soup.select(".film-outer"):
        title_tag = card.select_one(".liveeventtitle")
        if not title_tag:
            continue

        image_tag = card.select_one(".film_img img")
        detail_link = title_tag.get("href", "")
        running_values = [clean_filmhouse_text(span.get_text(" ", strip=True)) for span in card.select(".running-time span")]

        duration = ""
        rating = ""
        genre = ""
        for value in running_values:
            if re.search(r'\d+\s*mins?', value, re.IGNORECASE):
                duration = re.sub(r'\D+', '', value)
            elif value.startswith("(") and value.endswith(")"):
                rating = value.strip("()")
            elif not re.fullmatch(r'\d{4}', value):
                genre = value

        description_tag = card.select_one(".jacro-formatted-text")
        description = clean_filmhouse_text(description_tag.get_text(" ", strip=True)) if description_tag else ""
        times = []
        for booking_tag in card.select(".performance-list-items .film_book_button"):
            time_tag = booking_tag.select_one(".time")
            time_text = clean_filmhouse_text(time_tag.get_text(" ", strip=True)).upper() if time_tag else ""
            if time_text:
                times.append({
                    "time": time_text,
                    "bookingUrl": booking_tag.get("href", "")
                })

        if not times:
            continue

        movies.append({
            "title": clean_filmhouse_text(title_tag.get_text(" ", strip=True)),
            "image": image_tag.get("src", "") if image_tag else "",
            "link": detail_link,
            "rating": rating or "TBA",
            "duration": duration,
            "genre": genre,
            "description": description,
            "showtimes": [{
                "date": date_str,
                "location": "Golden Mile Tower",
                "times": times
            }]
        })

    return movies


def get_filmhouse_movies(scraper):
    print("Fetching Filmhouse showtimes for the next 7 days...")
    all_movies = []
    base_date = datetime.now()
    ajax_url = "https://filmhouse.sg/wp-admin/admin-ajax.php"

    headers = {
        "origin": "https://filmhouse.sg",
        "referer": "https://filmhouse.sg/",
        "x-requested-with": "XMLHttpRequest",
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    }

    for day_offset in range(7):
        target_date = (base_date + timedelta(days=day_offset)).strftime('%Y-%m-%d')
        payload = {
            "action": "jacrocalendarFilmfilter",
            "date": target_date
        }

        try:
            res = scraper.post(ajax_url, headers=headers, data=payload)
            if res.status_code == 200:
                data = res.json()
                daily_movies = parse_filmhouse_html(data.get("html", ""), target_date)
                all_movies.extend(daily_movies)
                print(f"  -> {target_date}: pulled {len(daily_movies)} Filmhouse movie entries.")
            else:
                print(f"  -> {target_date}: Filmhouse Failed: {res.status_code}")
        except Exception as e:
            print(f"  -> {target_date}: Filmhouse Error: {e}")

        time.sleep(0.5)

    print(f"  -> Collected {len(all_movies)} dated Filmhouse movie entries.")
    return all_movies


# ==========================================
# MAIN EXECUTION
# ==========================================

def main():
    print(f"=== Starting Cinema Scrape: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    scraper = cloudscraper.create_scraper()
    
    # 1. Gather Master Lists
    gv_master = get_gv_movies(scraper)
    shaw_data = get_shaw_movies(scraper) # Shaw already includes times
    eagle_master = get_eaglewings_movies(scraper)
    filmhouse_data = get_filmhouse_movies(scraper)
    
    # 2. Gather Detailed Timings for GV and EagleWings
    if gv_master:
        gv_detailed = get_gv_showtimes(scraper, gv_master)
    else:
        gv_detailed = []
        
    if eagle_master:
        eagle_detailed = get_eaglewings_showtimes(scraper, eagle_master)
    else:
        eagle_detailed = []
    
    # 3. Consolidate into the Final Dashboard Object
    dashboard_data = {
        "last_updated": datetime.now().isoformat(),
        "golden_village": gv_detailed,
        "shaw_theatres": shaw_data,
        "eagle_wings": eagle_detailed,
        "filmhouse": filmhouse_data
    }
    
    # 4. Save the file
    filename = 'cinema_dashboard_FULL.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(dashboard_data, f, indent=4)
        
    print(f"\n=== SUCCESS: All detailed data saved to {filename} ===")

if __name__ == "__main__":
    main()
