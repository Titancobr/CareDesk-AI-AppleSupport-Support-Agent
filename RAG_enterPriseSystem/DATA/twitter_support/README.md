# Twitter support data

`apple_support.csv` is an AppleSupport-only slice of Kaggle's
`thoughtvector/customer-support-on-twitter` dataset. It contains the actual
AppleSupport outbound replies plus inbound customer tweets linked to those
replies through `response_tweet_id`.

The source dataset is available at:
https://www.kaggle.com/datasets/thoughtvector/customer-support-on-twitter

The app looks for a `text` column and uses `author_id`, `inbound`, and
`response_tweet_id` to select Apple customer messages and their historical
AppleSupport replies. If the CSV is removed, it falls back to a small local
demo slice so the product walkthrough remains runnable offline.
