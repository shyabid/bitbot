from bs4 import BeautifulSoup
import requests

def scrape_discord_links():
    base_url = "https://discord.me/servers/category/investing?page="
    output_file = "discord_links.txt"
    class_name = "sc-link"
    seen_links = set()

    with open(output_file, "w") as file:
        for page in range(1, 201):
            url = base_url + str(page)
            response = requests.get(url)
            soup = BeautifulSoup(response.content, "html.parser")
            links = soup.find_all("a", class_=class_name)
            for link in links:
                full_link = f"https://discord.me{link['href']}"
                if full_link not in seen_links:
                    seen_links.add(full_link)
                    file.write(full_link + "\n")
                    file.flush()

if __name__ == "__main__":
    scrape_discord_links()


