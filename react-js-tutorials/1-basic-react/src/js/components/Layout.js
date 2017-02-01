import React from "react";
import axios from 'axios';
import Footer from "./Footer";
import Header from "./Header";

export default class Layout extends React.Component {
    constructor() {
        super();
        this.state = {
            title: "title -> Welcome_" + (3 + 5),
            msg: ''
        };
        this.name = "HIL";
        this.springboot = '';
    }

    getVal() {
        return 3 + '(int)';
    }

    componentDidMount() {
        axios.get('http://localhost:8080')
            .then(res => {
                console.log(res.data);
                this.setState(
                    {
                        msg: res.data
                    }
                )
            });
    }


    changeTitle(title) {
        this.setState({title});
    }

    render() {
        return (
            <div>
                <Header changeTitle={this.changeTitle.bind(this)} title={this.state.title}/>
                <h1> {this.name} {this.getVal()}  </h1>
                <h2> -> {"From Springboot: " + this.state.msg} {console.log(this.state.msg)} </h2>
                <Footer />
            </div>
        );
    }
}
