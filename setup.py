from setuptools import setup

setup(name='google_search',
      version='0.1',
      description='Scrapes Google Search webpages',
      url='https://bitbucket.org/flamingodf/google_search',
      author='Chris Daly',
      license='MIT',
      packages=['google_search'],
      install_requires=[
          'tqdm', 'pandas', 'bs4'
      ],
      zip_safe=False)
