FROM alpine
MAINTAINER Google Cloud Master hilliao@gmail.com
RUN apk update && apk add curl bind-tools
COPY dynu.sh /
CMD ["ash", "/dynu.sh"]