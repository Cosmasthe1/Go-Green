from providers import get_all_offers


def test_get_all_offers_returns_ranked_offers_for_route():
    offers = get_all_offers(-1.2921, 36.8219, -1.286, 36.841)

    assert len(offers) == 7
    assert [offer.provider for offer in offers] == [
        "Uber",
        "Bolt",
        "Yego",
        "Faras",
        "Little Cabs",
        "Wasili",
        "Weego",
    ]
    assert offers == sorted(offers, key=lambda offer: offer.price_kes)
