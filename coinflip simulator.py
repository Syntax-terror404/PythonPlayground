import random
number = int(input("Amounts of time you want to slip the coin:"))
heads = 0
tails = 0
outcomes = []
def coinflip():
    global heads, tails
    for _ in range(number):
        flips = random.randint(0, 1)
        if flips == 1:
            # if you want to see print("heads"), the code gets to redundant
            outcomes.append("heads")
            heads += 1
        else:
            # to avoid redundancy print("tails")
            outcomes.append("tails")
            tails += 1
coinflip()
print(f"\nFull list of outcomes:{outcomes}")
print(f"\nheads:{heads}"f"\ntails:{tails}")