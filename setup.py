from setuptools import setup, find_packages

setup(
    name = "django-segmented-uploads",
    version = "0.0.1",
    url = "https://github.com/thenewguy/django-segmented-uploads",
    packages=find_packages(),
    include_package_data=True,
    classifiers = [
        'Programming Language :: Python',
        'Operating System :: OS Independent',
        'Framework :: Django',
    ],
    extras_require={
        'testing': [
            'psycopg2-binary',
            'celery',
        ],
    },
    install_requires=[
        'django',
        'django-redis-cache',
    ],
)
