def checkPalindrome(str):
    if str is None:
        exit(10)
    i = 0
    j = len(str) - 1
    while i < j:
        if str[i] != str[j]:
            return False
        else:
            i += 1
            j -= 1
    return True


print("checkPalindrome result: " + str(+ checkPalindrome(" 漢字漢 ")))
print("checkPalindrome result: " + str(+ checkPalindrome(None)))
