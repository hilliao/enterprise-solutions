import numpy as np  # pip.exe install --user numpy
import math

a = np.matrix('1 2 3 4; 12 13 14 5; 11 16 15 6; 10 9 8 7')
# print(str(a.item(0, 1)) + "  size" + str(a.size))
n = math.sqrt(a.size)


def traverse(mat, pos):
    n = int(math.sqrt(mat.size))
    list = []
    '''
    :param mat: matrix to print
    :param pos: start from posotion at k,k for layer k
    :return:
    '''
    # add top
    for j in range(pos, n - pos):
        list.append(mat.item(pos, j))

    # add right
    for i in range(pos + 1, n - pos):
        list.append(mat.item(i, n - 1 - pos))

    # add bottom
    list_bottom = []
    for j in range(pos, n - pos - 1):
        list_bottom.append(mat.item(n - 1 - pos, j))
    list_bottom.reverse()
    list.extend(list_bottom)

    # add left
    list_left = []
    for i in range(pos + 1, n - pos - 1):
        list_left.append(mat.item(i, pos))
    list_left.reverse()
    list.extend(list_left)
    return list


# unit test 0
list0 = traverse(a, 0)
print(list0)


def traverse_matrix(mat):
    list = []

    n = int(math.sqrt(mat.size))
    pos_max = int(n / 2)
    for p in range(pos_max + 1):
        list.extend(traverse(mat, p))

    return list


print(traverse_matrix(a))
