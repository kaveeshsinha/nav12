"""Read-only vehicle catalogue; deliberately independent of Excel account storage."""
import json
from pathlib import Path
from flask import Blueprint, abort, render_template, request

CATALOGUE_DIR = Path(__file__).resolve().parent / 'catalogue'
DATA = json.loads((CATALOGUE_DIR / 'vehicles.json').read_text())
ASSETS = json.loads((CATALOGUE_DIR / 'assets.json').read_text())
ENGINES = {engine['slug']: engine for engine in json.loads((CATALOGUE_DIR / 'engines.json').read_text())}
BRANDS = {brand['slug']: brand for brand in DATA['brands']}
CARS = {car['slug']: car for car in DATA['cars']}
BY_BRAND = {slug: [car for car in CARS.values() if car['brand'] == slug] for slug in BRANDS}
BY_ENGINE = {slug: [car for car in CARS.values()
                    if all(car.get(key) == value for key, value in engine['selectors'].items())]
             for slug, engine in ENGINES.items()}
CHARACTERS = {
    'Sports car': 'Precision, balance and a close connection to the road.',
    'Grand tourer': 'Long-distance pace with room for a little comfort.',
    'Supercar': 'Extraordinary performance, unmistakable presence.',
    'Hypercar': 'Engineering at the outer edge of the collection.',
}
POWERTRAINS = {
    'Petrol': 'Combustion power, in very different forms.',
    'Plug-in hybrid': 'A combustion engine, electric motors and a rechargeable battery.',
}


def register_collection(app, login_required):
    catalogue = Blueprint('collection', __name__)

    @app.context_processor
    def collection_context():
        if request.endpoint == 'dashboard' or (request.endpoint or '').startswith('collection.'):
            return dict(gallery_brands=BRANDS, gallery_cars=CARS, cars_by_brand=BY_BRAND,
                        gallery_assets=ASSETS, engine_types=ENGINES, cars_by_engine=BY_ENGINE,
                        nav_characters=CHARACTERS, nav_powertrains=POWERTRAINS)
        return {}

    @catalogue.errorhandler(404)
    def not_found(error):
        return render_template('collection/not_found.html', title='Car not found'), 404

    @catalogue.get('/collection')
    @login_required
    def index():
        filters = {key: request.args.get(key, '').strip()[:120]
                   for key in ('q', 'brand', 'powertrain', 'character', 'engine')}
        cars = list(CARS.values())
        for key in ('brand', 'powertrain', 'character'):
            if filters[key]:
                cars = [car for car in cars if car[key] == filters[key]]
        if filters['engine']:
            matching = {car['slug'] for car in BY_ENGINE.get(filters['engine'], [])}
            cars = [car for car in cars if car['slug'] in matching]
        if filters['q']:
            query = filters['q'].casefold()
            cars = [car for car in cars if query in ' '.join(
                (BRANDS[car['brand']]['name'], car['name'], car['variant'],
                 car['engine'], str(car['year']))).casefold()]
        return render_template('collection/index.html', title='Car Collection', cars=cars,
                               filters=filters, filtered=any(filters.values()),
                               powertrains=sorted({c['powertrain'] for c in CARS.values()}),
                               characters=sorted({c['character'] for c in CARS.values()}),
                               featured=CARS['lamborghini-revuelto'])

    @catalogue.get('/engines')
    @login_required
    def engines():
        return render_template('collection/engines.html', title='Engine types',
                               groups=('Signature combinations', 'Cylinder layouts', 'Air & boost'))

    @catalogue.get('/engines/<engine_slug>')
    @login_required
    def engine(engine_slug):
        engine = ENGINES.get(engine_slug)
        if engine is None:
            abort(404)
        return render_template('collection/engine.html', title=engine['name'], engine=engine,
                               cars=BY_ENGINE[engine_slug])

    @catalogue.get('/brands/<brand_slug>')
    @login_required
    def brand(brand_slug):
        brand = BRANDS.get(brand_slug)
        if brand is None:
            abort(404)
        return render_template('collection/brand.html', title=brand['name'], brand=brand,
                               cars=BY_BRAND[brand_slug], featured=BY_BRAND[brand_slug][0])

    @catalogue.get('/cars/<car_slug>')
    @login_required
    def car(car_slug):
        car = CARS.get(car_slug)
        if car is None:
            abort(404)
        related = sorted((c for c in CARS.values() if c['slug'] != car_slug),
                         key=lambda c: (c['character'] != car['character'],
                                        c['brand'] != car['brand']))[:3]
        return render_template('collection/car.html', title=BRANDS[car['brand']]['name'] + ' ' + car['name'],
                               car=car, brand=BRANDS[car['brand']], related=related)

    @catalogue.get('/collection/credits')
    @login_required
    def credits():
        return render_template('collection/credits.html', title='Photography & sources')

    app.register_blueprint(catalogue)
