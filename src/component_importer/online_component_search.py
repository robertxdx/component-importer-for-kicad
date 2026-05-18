# Import dataclass to create simple result objects
from dataclasses import dataclass

# Import quote_plus to safely encode search text for URLs
from urllib.parse import quote_plus

# Import webbrowser to open search results in the default browser
import webbrowser


# Store one online component search result
@dataclass
class OnlineSearchResult:
    # Name of the provider, for example SnapMagic or DigiKey
    provider: str

    # Type of result, for example CAD models, product data, datasheet, stock
    result_type: str

    # Search URL
    url: str

    # Short note shown to the user
    note: str


# Build online search URLs for a component MPN or keyword
def build_component_search_results(query: str) -> list[OnlineSearchResult]:
    # Clean query text
    query = query.strip()

    # Stop if query is empty
    if not query:
        raise ValueError("Search query cannot be empty.")

    # Encode query so it can safely be used inside URLs
    encoded_query = quote_plus(query)

    # Store all provider search results
    results = [
        OnlineSearchResult(
            provider="SnapMagic / SnapEDA",
            result_type="CAD models",
            url=f"https://www.snapeda.com/search/?q={encoded_query}",
            note="Good source for symbols, footprints, and 3D models.",
        ),
        OnlineSearchResult(
            provider="ComponentSearchEngine / SamacSys",
            result_type="CAD models",
            url=f"https://componentsearchengine.com/search?term={encoded_query}",
            note="Good source for KiCad symbols, footprints, and 3D models.",
        ),
        OnlineSearchResult(
            provider="Ultra Librarian",
            result_type="CAD models",
            url=f"https://app.ultralibrarian.com/search?queryText={encoded_query}",
            note="Good source for ECAD models and 3D models.",
        ),
        OnlineSearchResult(
            provider="DigiKey",
            result_type="Product data",
            url=f"https://www.digikey.com/en/products/result?keywords={encoded_query}",
            note="Good for product data, datasheets, stock, pricing, and MPN validation.",
        ),
        OnlineSearchResult(
            provider="Mouser",
            result_type="Product data",
            url=f"https://eu.mouser.com/c/?q={encoded_query}",
            note="Good for product data, datasheets, stock, pricing, and ECAD links.",
        ),
        OnlineSearchResult(
            provider="Octopart",
            result_type="Product search",
            url=f"https://octopart.com/search?q={encoded_query}",
            note="Good for cross-distributor component search.",
        ),
    ]

    # Return all search results
    return results


# Print search results in a readable format
def print_component_search_results(results: list[OnlineSearchResult]) -> None:
    # If there are no results, print a clear message
    if not results:
        print("No search results.")
        return

    # Loop through all search results
    for index, result in enumerate(results, start=1):
        # Print result number and provider
        print(f"{index}. {result.provider}")

        # Print result type
        print(f"   Type: {result.result_type}")

        # Print note
        print(f"   Note: {result.note}")

        # Print URL
        print(f"   URL: {result.url}")

        # Add empty line for readability
        print()


# Open one search result in the default browser
def open_search_result(results: list[OnlineSearchResult], index: int) -> None:
    # Check that the index is valid
    if index < 1 or index > len(results):
        raise IndexError(f"Result index must be between 1 and {len(results)}.")

    # Get selected result
    result = results[index - 1]

    # Open the URL in the default browser
    webbrowser.open(result.url)


# Open all CAD provider searches in browser tabs
def open_cad_searches(results: list[OnlineSearchResult]) -> None:
    # Loop through all results
    for result in results:
        # Open only CAD model providers
        if "CAD" in result.result_type:
            webbrowser.open(result.url)


# Create search results and print them in one call
def search_component_online(query: str) -> list[OnlineSearchResult]:
    # Build result list
    results = build_component_search_results(query)

    # Print readable output
    print_component_search_results(results)

    # Return result list so the user can open selected links
    return results