The Rolling Pin
===============

<img src="https://upload.wikimedia.org/wikipedia/commons/1/19/Work_dough.jpg" width="280" height="210" align="right" alt="">

A tool for rolling changes out to servers.

To roll stuff out, select a group of hosts to affect:

* a master list of hosts is collected by the "host source" which is pluggable.
* aliased hostname glob expressions specify which hosts to pay attention to (`-h`)
* the list may be truncated by starting after (`--startat`) or stopping before
  (`--stopbefore`) specified hosts

And what commands you'd like to run:

* components to deploy get built on configurable build servers then deployed to
  individual hosts (`-d`)
* restart services (`-r`)
* arbitrary other commands may be specified as long as the remote end knows how
  to execute them (`-c`)

The rollout will then begin:

* rollouts are executed by the "transport" which is pluggable and defaults to ssh.
* hosts are "enqueued" one at a time with an optional delay between them
  (`--sleeptime`)
* multiple hosts can be worked on in parallel (`--parallel`)
* after a number of hosts have completed their work, the rollout can pause to
  allow [sanity checking][1] before continuing on (`--pauseafter`)

If configured, graphite will be sent a metric of the form
`events.deploy.{component}` for each component deployed.

The rolling pin also features integration with [Harold][2].

Setup
-----

To install:

```
https://github.com/reddit/rollingpin.git
python setup.py install
```

Next, copy `example.ini` to `/etc/rollingpin.ini` or `~/.rollingpin.ini`, modifying the hostsource to suit your environment.

For example, to set up an alias and deploy to 3 static hosts:

```ini
[hostsource]
provider = mock
hosts = host1 host2 host3

[aliases]
myhosts = host*
```

The hosts you are deploying to must have a local deploy script ready to be
executed.  You can use `example-deploy.py` as a starting point.

Once your deploy script is in place, update your configuration with its path:

```ini
[transport]
command = /usr/local/bin/deploy
```

When deploying, the deploy script will be called with the desired command on
the command line.

For instance:

```ini
rollout -h myhosts -c foo
```

will call:

```ini
sudo /usr/local/bin/deploy foo
```

on the hosts matched by the `myhosts ` alias.


Development
-----

A `Vagrantfile` is included which sets up a testing environment that uses a
mock hostsource and transport so that you can simulate deploys to non-existent
hosts.

```
# launch the environment
host$ vagrant up
host$ vagrant ssh

# "deploy" to the full list of servers
rollingpin$ rollout test

# "deploy" to smaller subsets of servers
rollingpin$ rollout test -h common
rollingpin$ rollout test -h medium
rollingpin$ rollout test -h rare
rollingpin$ rollout test -h singular

# run the test suite
rollingpin$ cd rollingpin/
rollingpin$ python setup.py test
```

You can also run the test and lint suites in a Docker container:

```bash
docker build . -t rollingpin:test && docker run --rm rollingpin:test
```

[1]: http://i.imgur.com/66Nr9Wo.jpg
[2]: https://github.com/spladug/harold
