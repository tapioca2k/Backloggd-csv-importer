# Backloggd.com csv Importer

Quick and dirty Python script for importing games from a csv file into [Backloggd.com](https://www.backloggd.com).
You will almost certainly need to adapt the code a little bit to make it work for your needs.

## backloggd.json
Next to the python script should be a configuration file, `backloggd.json`, set up as follows:
```
{
	id: [IGDB API ID],
	secret: [IGDB API Secret],
	backloggd_id: [Backloggd account ID],
	csrf: [Backloggd csrf token],
	cookie: [Backloggd cookie]
}
```
Your backloggd account ID can be found by inspecting most requests made on the site in a browser.
The csrf token can be found by inspecting the source on most site pages, or in most requests.
The cookie can be found in your browser's cookie settings. You are looking for the value to the key "_august_app_session".
Note that the csrf and cookie tokens do expire, but not for a while. You should have no issue importing all your games at once before they need replacing.

## csv format
An example csv is provided. The default format is below, although it is very easy to adjust the code for your own needs.

Game Name | (Blank) | Release Year | (Blank) | (Blank) | Rating (out of 5)
----------|---------|--------------|---------|---------|---------
Jak 3 | | 2004 | | | 2
Katamari Damacy | | 2004 | | | 5
Tomb Raider | | 2013 | | | 2
