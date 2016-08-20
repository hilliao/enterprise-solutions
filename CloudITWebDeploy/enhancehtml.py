import sys
import os

included_extenstions = ['html']
basePath = "\\\\ubuntu\\cloudit"
if not os.path.exists(basePath):
    print("base path %s does not exist" % basePath)
    sys.exit(1)

html_file_names = [os.path.join(basePath, fn) for fn in os.listdir(basePath)
                   if any(fn.endswith(ext) for ext in included_extenstions)]
line2delete = None
line2add = None

for html_file_name in html_file_names:
    htmlFile = open(html_file_name, 'r+')
    htmlContent = htmlFile.readlines()
    for item in htmlContent:
        if item.find('<div id="footer">Create a <a target="_top" href="http://www.weebly.com/">free web site') != -1:
            line2delete = item
        if item.find('<body ') != -1:
            line2add = item

    if line2delete is None:
        htmlFile.close()
        print("no weebly footer found in file %s" % html_file_name)
        sys.exit(2)

    if line2add is None:
        htmlFile.close()
        print("no <body  found in file %s" % html_file_name)
        sys.exit(2)

    # remove the undesired lines Weebly created
    lineIndex = htmlContent.index(line2delete)
    htmlContent[lineIndex] = ''
    htmlContent[lineIndex + 1] = ''

    # add facebook SDK scripts
    indexOfBody = htmlContent.index(line2add)
    jsFile = open("script.html", 'r')
    jsContent = jsFile.read()
    jsFile.close()
    htmlContent[indexOfBody] += jsContent + "\n"

    # add facebook like button in the index page
    if html_file_name.find("index.htm") != -1:
        indexOfSuccessStories = htmlContent.index(
            '<h2 class="wsite-content-title" style="text-align:center;"><font size="6">SUCCESS STORIES</font></h2>\n')
        jsFile = open('sharebutton.html', 'r')
        jsContent = jsFile.read()
        jsFile.close()
        htmlContent[indexOfSuccessStories] += jsContent

    # writing to the file
    htmlFile.seek(0)
    replaced = "".join(htmlContent).replace("www.weebly.com", "hil.dlinkddns.com")
    htmlFile.write(replaced)
    htmlFile.truncate()
    htmlFile.close()

# after successful execution, delete the site and run the following to upload to the website
# UI to delete site at https://console.cloud.google.com/storage/browser/cloudit/?project=hil-micro-use
# gsutil cp -r /var/www/html/cloudit/* gs://cloudit/site/
