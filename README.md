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
For local dev, you can run all tests/lint in a local docker container by:
```bash
docker build . -t rollingpin:test && docker run --rm rollingpin:test
```


[1]: http://i.imgur.com/66Nr9Wo.jpg
[2]: https://github.com/spladug/harold

Deploy Commands
-----
While any arbitrary command can be supported by your deploy script,
there are a few that rollingpin has special support for.

### build ###

If ``build-host`` is present in the root directory of your project, rollingpin
will attempt to connect to that host and run the following:

    deploy-script build foo@01234567 bar@abcdef

Where each argument passed is the name of a deploy target and the SHA that
will be deployed.  The build command in your deploy script should take these
arguments, do whatever building is necessary, and return a result in the
format:

    {
        'foo@012345': '012345',
        'bar@abcdef': 'abcdef',
    }

### component_report ###

The ``component_report`` command collects information about the SHA of each
running process across all target hosts.  It can be used to identify hanging
processes.  A summary report will be a printed to stdout, in the format:

    *** component report
    COMPONENT      SHA     COUNT
    foo         012345      1
    bar         abcdef      1

To support this functionality, the ``component_report`` in your deploy script
should return a result containing all running SHAs of all components on the
host, in the format:

    {
        'components': {
            'foo': '012345',
            'bar': 'abcdef',
        }
    }

The ``component_report`` in your deploy script should also print more detailed
information to **stderr** to allow an operator to dig in further if a problem is
found.  The suggested format of this output:

    component: app-123 foo@012345
    component: app-123 bar@abcdef
