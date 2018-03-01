import re, math
from bisect import bisect_left

def pickConfig(desiredMemory, myList=[2**x for x in range(8)]):
    # TODO: needs a switch to output MB for openvz default configs
    """
    myList is all the available VZ configs. Returns left value to desiredMemory.
    If two numbers are equally close, return the smallest number.
    returns int (in GB) of the VZ config to use
    """
    myList.sort()
    pos = bisect_left(myList, desiredMemory)
    before = myList[pos - 1]
    after = myList[pos]
    result = 0
    if desiredMemory - after == 0:
        result = after
    else:
        result = before

    return int(result)


def roundUp(x, y):
    """
    Round up x to next y interval
    """
    return int(math.ceil(x/(y * 1.0)) * y)


def storageUnits(disksize, min_interval):
    """
    The disksize should be a string with G or M to represent which measure to use
    disksize will be normalized in min_interval chunks.  returns the storage_units 
    that will be used in addition to the space requested
    """
    separate = re.findall(r"^\d+|[^\W\d_]$", str(disksize))
    size = int(separate[0])
    num = 0

    # convert to Mb and round to next min_interval
    try:
        bits = separate[1].upper()
        if bits == "G":
            num = roundUp(size << 10, min_interval)
        elif bits == "M":
            num = roundUp(size, min_interval)
    except IndexError:
        # assume M if not specified
        num = roundUp(size, min_interval)

    # divide by min_interval to get storage units, should be clean int due to roundUp()
    units = num / min_interval

    return units, num
