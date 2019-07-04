FROM ubuntu:16.04

ENV DEBIAN_FRONTEND noninteractive
ENV LC_ALL C.UTF-8
ENV LANG C.UTF-8
# Python, don't write bytecode!
ENV PYTHONDONTWRITEBYTECODE 1

RUN apt-get update
RUN apt-get install -y software-properties-common git curl apt-transport-https
RUN add-apt-repository ppa:jonathonf/python-3.6
RUN apt-get update

RUN apt-get install -y build-essential python3.6 python3.6-dev python3-pip python3.6-venv

# update pip
RUN python3.6 -m pip install pip --upgrade
RUN python3.6 -m pip install wheel

RUN curl --silent https://bootstrap.pypa.io/get-pip.py | python3.6

# Backwards compatility.
RUN rm -fr /usr/bin/python3 && ln /usr/bin/python3.6 /usr/bin/python3

# Node
RUN curl -sL https://deb.nodesource.com/setup_10.x | bash -
RUN apt-get install -y nodejs

# Yarn
RUN curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add -
RUN echo "deb https://dl.yarnpkg.com/debian/ stable main" | tee /etc/apt/sources.list.d/yarn.list

RUN apt-get update && apt-get -y install yarn

# -- Install Application into container:
RUN set -ex && mkdir /app

WORKDIR /app

COPY . /app

RUN set -ex && pip3 install -r requirements.txt

RUN yarn
RUN yarn build

RUN make generate-version-file

CMD ["flask", "run", "-p", "6012", "--host=0.0.0.0"]