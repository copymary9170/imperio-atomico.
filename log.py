import datetime


def log(mensaje):

    with open("log.txt", "a", encoding="utf8") as f:

        f.write(f"{datetime.datetime.now()} - {mensaje}\n")
