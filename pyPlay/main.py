import os


def minmax(a, b, c, d, e):
    ex_a = b + c + d + e
    ex_b = a + c + d + e
    ex_c = a + b + d + e
    ex_d = a + b + c + e
    ex_e = a + b + c + d
    return min(ex_a, ex_b, ex_c, ex_d, ex_e), max(ex_a, ex_b, ex_c, ex_d, ex_e)


def count(s):
    indexRange = range(len(s))
    countMirrored = 0
    for start in indexRange:
        if start == len(s) - 1:
            continue;

        for end in indexRange[start + 1:-1]:
            binaryMirroredCandidate = s[start:end + 1]
            i = 0
            j = len(binaryMirroredCandidate) - 1
            binaryMirrored = True
            while (i < j):
                if binaryMirroredCandidate[i] == binaryMirroredCandidate[j]:
                    binaryMirrored = False
                i += 1
                j -= 1
            if binaryMirrored:
                countMirrored += 1
    return countMirrored


# Show a simple message.
# counted = count('0011')
# print('count is ' + counted)
min_max = minmax(3, 6, 987, 545, 1)
print(str(min_max[0]) + " " + str(min_max[1]))
