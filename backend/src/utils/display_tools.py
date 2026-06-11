import pprint


def pprint_df(df):
    pprint.pprint(df.to_dict(orient="records"))
